from rl.eval_shadow import run_shadow_eval


def main():
    report = run_shadow_eval()
    print(report)


if __name__ == "__main__":
    main()
