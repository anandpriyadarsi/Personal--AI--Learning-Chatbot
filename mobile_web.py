"""Explicit private-mobile launcher. No public binding or paid infrastructure."""
import logging
import os


def main():
    os.environ['ANVAYA_PRIVATE_MOBILE'] = 'true'
    # Do not log academic URLs, IDs or query text to the console.
    logging.getLogger('werkzeug').disabled = True
    from personal_learning_assistant.ui.web.__main__ import main as run_local
    run_local()


if __name__ == '__main__':
    main()
