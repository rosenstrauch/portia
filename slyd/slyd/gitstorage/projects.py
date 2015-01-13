import json
from os.path import join
from functools import wraps

from twisted.internet.threads import deferToThread

from slyd.projects import ProjectsManager
from slyd.projecttemplates import templates
from slyd.errors import BadRequest
from .repoman import Repoman


def run_in_thread(func):
    '''A decorator to defer execution to a thread'''

    @wraps(func)
    def wrapper(*args, **kwargs):
        return deferToThread(func, *args, **kwargs)

    return wrapper


class GitProjectsManager(ProjectsManager):

    @classmethod
    def setup(cls, storage_backend, location):
        Repoman.setup(storage_backend, location)

    def __init__(self, *args, **kwargs):
        ProjectsManager.__init__(self, *args, **kwargs)
        self.project_commands = {
            'create': self.create_project,
            'mv': self.rename_project,
            'rm': self.remove_project,
            'edit': self.edit_project,
            'publish': self.publish_project,
            'discard': self.discard_changes,
            'revisions': self.project_revisions,
            'conflicts': self.conflicted_files,
            'changes': self.changed_files,
            'save': self.save_file,
        }

    def _open_repo(self, name):
        return Repoman.open_repo(name)

    def _get_branch(self, repo, read_only=False):
        if repo.has_branch(self.user):
            return self.user
        elif not read_only:
            repo.create_branch(self.user, repo.get_branch('master'))
            return self.user
        else:
            return 'master'

    def all_projects(self):
        return Repoman.list_repos()

    def create_project(self, name):
        self.validate_project_name(name)
        project_files = {
            'project.json': templates['PROJECT'],
            'scrapy.cfg': templates['SCRAPY'],
            'setup.py': templates['SETUP'] % str(name),
            join('spiders', '__init__.py'): '',
            join('spiders', 'settings.py'): templates['SETTINGS'],
        }
        try:
            Repoman.create_repo(name).save_files(project_files, 'master')
        except NameError:
            raise BadRequest("Bad Request",
                             "Project already exists with that name")

    def remove_project(self, name):
        Repoman.delete_repo(name)

    def edit_project(self, name, revision):
        # Do nothing here, but subclasses can use this method as a hook
        # e.g. to import projects from another source.
        return

    @run_in_thread
    def publish_project(self, name, force):
        repoman = self._open_repo(name)
        if repoman.publish_branch(self._get_branch(repoman), force):
            repoman.kill_branch(self._get_branch(repoman))
            return 'OK'
        else:
            return 'CONFLICT'

    def discard_changes(self, name):
        repoman = self._open_repo(name)
        repoman.kill_branch(self._get_branch(repoman))

    def project_revisions(self, name):
        repoman = self._open_repo(name)
        return json.dumps({'revisions': repoman.get_published_revisions()})

    @run_in_thread
    def conflicted_files(self, name):
        repoman = self._open_repo(name)
        return json.dumps(
            repoman.get_branch_conflicted_files(
                self._get_branch(repoman, read_only=True)))

    @run_in_thread
    def changed_files(self, name):
        repoman = self._open_repo(name)
        return json.dumps(repoman.get_branch_changed_files(
            self._get_branch(repoman, read_only=True)))

    def save_file(self, name, file_path, file_contents):
        repoman = self._open_repo(name)
        repoman.save_file(file_path, json.dumps(
            file_contents,
            sort_keys=True, indent=4), self._get_branch(repoman))