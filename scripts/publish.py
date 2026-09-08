"""Publish to the existing Git remote; never create a repository or account."""
from pathlib import Path
import subprocess
import sys
from travel_core import ROOT, TravelError, build

# Stage only project files; backups, exports and build_private are never added.
PUBLISH_PATHS = ['build', 'data/points.csv', 'data/routes.csv', 'data/routes',
                 'scripts/travel_core.py', 'scripts/project_lock.py',
                 'scripts/travel_manager.py', 'scripts/build_map.py',
                 'scripts/add_point.py', 'scripts/publish.py',
                 'scripts/extract_from_umap.py',
                 'Start.cmd', 'setup.cmd', 'publish.ps1', 'requirements.txt',
                 'README.md', 'map_config.json', '.gitignore',
                 'tests/test_workflow.py', 'tests/test_route_import.py', 'docs/UPGRADE.md', 'docs/ROUTES.md']


def git(root, *args, check=True):
    try:
        p = subprocess.run(['git', *args], cwd=root, text=True, encoding='utf-8',
                           errors='replace', capture_output=True, timeout=120)
    except FileNotFoundError:
        raise TravelError('Git is not installed or is not on PATH.') from None
    except subprocess.TimeoutExpired:
        raise TravelError('Git timed out. Check connectivity and Git credentials, then retry.') from None
    if check and p.returncode:
        raise TravelError((p.stderr or p.stdout).strip() or f'Git failed: {args[0]}')
    return p


def publish(root=ROOT):
    root = Path(root)
    git(root, 'rev-parse', '--show-toplevel')
    upstream = git(root, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}').stdout.strip()
    if not upstream:
        raise TravelError('No upstream configured. Use your existing repository folder with its Git setup.')
    def allowed(path):
        return any(path == p or (p in ('build', 'data/routes') and path.startswith(p+'/')) for p in PUBLISH_PATHS)
    staged = git(root, 'diff', '--cached', '--name-only', '-z').stdout.split('\0')
    other = [p for p in staged if p and not allowed(p)]
    if other:
        raise TravelError('Unrelated files are already staged. Unstage them before publishing:\n'+'\n'.join(other))
    message = build(root)
    paths = [p for p in PUBLISH_PATHS if (root/p).exists()]
    git(root, 'add', '-A', '--', *paths)
    changes = git(root, 'diff', '--cached', '--quiet', check=False)
    if changes.returncode == 1:
        git(root, 'commit', '-m', 'Update travel log')
    elif changes.returncode != 0:
        raise TravelError(changes.stderr or 'Could not check staged changes.')
    # Retry an earlier unpushed commit even if this build changed nothing.
    git(root, 'push')
    return message + '\nPushed to the existing Git remote.\nAllow hosting to update, then refresh uMap. Only layers linked to remote GeoJSON refresh automatically.'


if __name__ == '__main__':
    try:
        from project_lock import project_lock
        with project_lock(ROOT):
            print(publish())
    except (TravelError, OSError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
