from ml.decay_dataset import build_decay_dataset
from core.reports.decay_report import run_decay_report


def main():
    build_decay_dataset()
    report = run_decay_report()
    print(report)


if __name__ == "__main__":
    main()
