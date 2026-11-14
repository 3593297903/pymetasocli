"""Own-name installation; preflight all destinations and never replace user edits."""
import shutil
from importlib.resources import files
from pathlib import Path

from ..domain.errors import AppError
from ..persistence.codec import sealed, sha256, verify
from ..persistence.files import (
    atomic_write,
    lock,
    project_path,
    read_json,
    read_stable,
    safe_path,
    write_json,
)

NAMES = ('metasocli-py', 'metasocli-py-video-prompts', 'metasocli-py-video-prompts-旁白',
         'metasoclitk-py', 'metasocli-py-prompt-engine', 'metasocli-py-reference-images')
ENTRIES = NAMES[1:4]


def payloads() -> dict[str, bytes]:
    result = {}
    def visit(node, prefix):
        for child in node.iterdir():
            path = prefix + child.name
            if child.is_dir():
                visit(child, path + '/')
            else:
                result[path] = child.read_bytes()
    visit(files('metasocli_py.resources').joinpath('skills'), '')
    return result


def install(user_dir: Path) -> dict:
    destination = safe_path(user_dir)
    destination.mkdir(parents=True, exist_ok=True)
    record = destination / '.metasocli-py-install.json'
    package = payloads()
    outputs = {}
    for name in ENTRIES:
        outputs[name + '/SKILL.md'] = package[name + '/SKILL.md']
        for path, content in package.items():
            if path.startswith(name + '/references/'):
                outputs[path] = content
        for path, content in package.items():
            outputs[name + '/references/package/' + path] = content
    with lock(destination / '.metasocli-py-install.lock'):
        if record.exists():
            prior = verify(read_json(record))
            if prior['owner'] != 'metasocli-py' or prior['files'] != {p: sha256(b) for p, b in outputs.items()}:
                raise AppError('SKILL_INSTALL_CONFLICT', 'Existing install differs; uninstall the verified own install first.')
            for path, expected in prior['files'].items():
                if sha256(read_stable(project_path(destination, path))) != expected:
                    raise AppError('SKILL_INSTALL_CONFLICT', 'Installed files were edited; preserve user changes.')
            return {'installed': list(ENTRIES), 'alreadyInstalled': True}
        if any((destination / name).exists() for name in ENTRIES):
            raise AppError('SKILL_INSTALL_CONFLICT', 'A destination already exists; nothing overwritten.')
        # Durable ownership intent permits rollback after interrupted file copies.
        write_json(record, sealed({'owner': 'metasocli-py', 'files': {p: sha256(b) for p, b in outputs.items()}}))
        for path, content in outputs.items():
            atomic_write(project_path(destination, path), content)
    return {'installed': list(ENTRIES), 'selectorObserved': False}


def uninstall(user_dir: Path) -> dict:
    destination = safe_path(user_dir)
    record = destination / '.metasocli-py-install.json'
    with lock(destination / '.metasocli-py-install.lock'):
        prior = verify(read_json(record))
        if prior['owner'] != 'metasocli-py':
            raise AppError('SKILL_INSTALL_CONFLICT', 'Not owned by metasocli-py.')
        for path, expected in prior['files'].items():
            target = project_path(destination, path)
            if path.split('/')[0] not in ENTRIES or (target.exists() and sha256(read_stable(target)) != expected):
                raise AppError('SKILL_INSTALL_CONFLICT', 'User changes prevent automatic rollback.')
        for name in ENTRIES:
            target = project_path(destination, name)
            if target.exists():
                actual = {p.relative_to(destination).as_posix() for p in target.rglob('*') if p.is_file()}
                if actual - prior['files'].keys():
                    raise AppError('SKILL_INSTALL_CONFLICT', 'Unowned files prevent rollback.')
        for name in ENTRIES:
            target = project_path(destination, name)
            if target.exists():
                shutil.rmtree(target)
        record.unlink()
    return {'removed': list(ENTRIES)}


def skills_command(args) -> dict:
    if args.action == 'list':
        return {'skills': list(NAMES), 'userEntries': list(ENTRIES)}
    if args.action == 'read':
        if args.name not in NAMES:
            raise AppError('SKILL_NOT_FOUND', 'Unknown packaged skill.')
        return {'name': args.name, 'text': payloads()[args.name + '/SKILL.md'].decode('utf-8')}
    return install(args.user_dir) if args.action == 'install' else uninstall(args.user_dir)
