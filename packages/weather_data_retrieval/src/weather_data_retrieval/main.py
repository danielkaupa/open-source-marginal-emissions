if __name__ == "__main__" and __package__ is None:
    import os, sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ----------------------------------------------
# LIBRARY IMPORTS
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION IMPORTS
# ----------------------------------------------

from weather_data_retrieval.io.cli import parse_args, run_prompt_wizard
from weather_data_retrieval.io.config_loader import load_and_validate_config
from weather_data_retrieval.utils.session_management import SessionState
from weather_data_retrieval.runner import run
from weather_data_retrieval.utils.logging import setup_logger, log_msg
from weather_data_retrieval.utils.data_validation import default_save_dir

# ----------------------------------------------
# CONSTANTS AND SHARED VARIABLES
# ----------------------------------------------

# N/A

# ----------------------------------------------
# FUNCTION DEFINITIONS
# ----------------------------------------------


def main():
    args = parse_args()
    session = SessionState()

    run_mode = "automatic" if args.config else "interactive"
    verbose = bool(args.verbose) if run_mode == "automatic" else True  # interactive is always verbose

    # Initialize logger (console handler is attached when interactive or verbose)
    logger = setup_logger(str(default_save_dir), run_mode=run_mode, verbose=verbose)

    try:
        if run_mode == "automatic":
            config = load_and_validate_config(args.config)
            exit_code = run(config, run_mode=run_mode, verbose=verbose, logger=logger)
        else:
            # Wizard handles its own console echo; we still attach console handler via verbose=True above
            completed = run_prompt_wizard(session, logger=logger)
            if not completed:
                return
            config = session.to_dict()
            exit_code = run(config, run_mode=run_mode, verbose=True, logger=logger)

        # No extra print logic here; runner handles final summary echoing

    except Exception as e:
        # Runner also handles exceptions; this is just a fallback
        if logger:
            logger.exception(f"Critical error: {e}")
        else:
            print(f"Critical error: {e}")

if __name__ == "__main__":
    main()