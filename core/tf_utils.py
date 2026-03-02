import os
import subprocess
import sys


def configure_tensorflow():
    """Configure TensorFlow runtime to avoid XLA metric crashes in some environments."""
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    os.environ.setdefault("TF_XLA_FLAGS", "--tf_xla_auto_jit=0")
    os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
    try:
        import tensorflow as tf  # noqa: F401
        try:
            tf.config.optimizer.set_jit(False)
        except Exception:
            pass
    except Exception:
        # TensorFlow not installed or not imported yet
        pass


def check_tf_available(timeout_sec=5) -> bool:
    """
    Verify TensorFlow importability in an isolated subprocess.

    This prevents the main UI process from hanging on heavy or broken TF imports.
    """
    try:
        timeout = max(1.0, float(timeout_sec))
    except Exception:
        timeout = 5.0
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    try:
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2'); import tensorflow as tf; print(tf.__version__)",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return probe.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False
