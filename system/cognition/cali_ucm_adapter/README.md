# CALI-UCM Adapter

This adapter is a controlled ORB trial surface for the sovereign CALI-UCM source repository.

Source repository:

```text
R:\CALI-UCM
```

Adapter location:

```text
R:\Orb_Assistant_Desktop\system\cognition\cali_ucm_adapter
```

The adapter does not copy CALI-UCM source files. TypeScript resolves CALI-UCM through the `@cali-ucm` paths alias in `tsconfig.json`.

## Feature Flag

The adapter is inactive unless:

```text
CALI_UCM_ENABLED=true
```

If the flag is missing or any value other than `true`, adapter calls return a disabled result and existing ORB runtime behavior remains unchanged.

This adapter is not the default ORB cognition runtime path.
