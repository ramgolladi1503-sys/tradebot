# V33A runtime-root contract

For candidate `f44e637f4fea04dd824f47cf4a0202840be3ff1d`, live runtime data must be rooted at:

`/Volumes/TradeBotData/live-verification-f44e637-<session>/`

or an explicitly governed equivalent whose resolved path is below `/Volumes/TradeBotData`, whose device ID equals the mounted volume device, and which passes a writable temporary-file probe in that same directory.

Required startup assertions:

1. volume exists and is a directory;
2. resolved runtime root is below the expected volume;
3. runtime root and volume have the same device ID;
4. runtime root is writable;
5. same-directory temporary creation succeeds;
6. no fallback path is selected;
7. all configured DB/log/report/lock/export paths resolve below the runtime root or an explicitly approved external child;
8. compatibility mirrors are disabled or explicitly redirected to the same root.

Any failed assertion is a startup `BLOCKED`/fail-closed result. It must not start or continue live collection.
