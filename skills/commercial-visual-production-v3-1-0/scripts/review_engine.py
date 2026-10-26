"""V3 entrypoint; V2 command compatibility is isolated in compat/v2."""
from workflow import main
if __name__=="__main__":
    raise SystemExit(main())
