import os


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
