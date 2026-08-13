from pathlib import Path
from radar_cgr.pipeline import main
from radar_cgr.fusion_export import build

if __name__ == "__main__":
    main()
    print(build(Path(__file__).resolve().parent))
