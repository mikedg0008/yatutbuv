"""Retired one-time migration entry point; deliberately refuses to overwrite data."""
if __name__ == '__main__':
    raise SystemExit(
        'Migration is disabled in the upgraded project to protect current records.\n'
        'Use Start.cmd to edit data. Your original uMap backup remains in backups/.\n'
        'If you need a fresh migration, use a separate empty project and the original script from Git history.'
    )
