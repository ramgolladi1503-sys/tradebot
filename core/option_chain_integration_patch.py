# PATCH GUIDE: integrate live kite chain into option_chain.py

from core.kite_option_chain_live import KiteLiveOptionChainBuilder


def fetch_option_chain_with_live(symbol, spot, context, synthetic_fn):
    """
    Wrapper to inject live kite chain safely without breaking existing system.
    """

    # 1. try live chain
    if context.get("live") and context.get("broker_ok"):
        try:
            builder = KiteLiveOptionChainBuilder()
            chain = builder.build(symbol=symbol, spot=spot)

            if chain and len(chain) > 0:
                return chain

        except Exception as e:
            print(f"[CHAIN] live failed → fallback: {e}")

    # 2. fallback to synthetic (existing system)
    return synthetic_fn(symbol, spot, context)


# HOW TO USE (inside your existing option_chain.py)

# Replace your existing fetch logic with:
#
# def fetch_option_chain(symbol, spot, context):
#     return fetch_option_chain_with_live(
#         symbol=symbol,
#         spot=spot,
#         context=context,
#         synthetic_fn=existing_synthetic_chain_function
#     )
