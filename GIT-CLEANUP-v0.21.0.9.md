# Git cleanup for updated v0.21.0.9

The current GitHub `main` tree contains old hashed frontend cache assets from the initially published v0.21.0.9 build. Remove only the obsolete hashed files listed below before/with the new commit.

## Delete from Git

```text
custom_components/bitcoin_stack_tracker/frontend/index-v021009-3c9a03c7.html
custom_components/bitcoin_stack_tracker/frontend/panel-v021006-733b783d.js
custom_components/bitcoin_stack_tracker/frontend/static/app-v021009-1ef3c90f.js
custom_components/bitcoin_stack_tracker/frontend/static/style-v021006-733b783d.css
```

## Keep

```text
custom_components/bitcoin_stack_tracker/frontend/panel-v021009-ae7b9cb3.js
custom_components/bitcoin_stack_tracker/frontend/static/performance-math-v021006-733b783d.js
custom_components/bitcoin_stack_tracker/frontend/index.html
custom_components/bitcoin_stack_tracker/frontend/static/app.js
custom_components/bitcoin_stack_tracker/frontend/static/style.css
custom_components/bitcoin_stack_tracker/frontend/static/performance-math.js
```

The unversioned files are overwritten by the new build. `panel-v021009-ae7b9cb3.js` remains valid and is still the active panel module. The versioned performance-math asset also remains unchanged and referenced.

## New hashed assets

The final replacement assets are:

```text
custom_components/bitcoin_stack_tracker/frontend/index-v021009-cacd75ff.html
custom_components/bitcoin_stack_tracker/frontend/panel-v021009-ae7b9cb3.js
custom_components/bitcoin_stack_tracker/frontend/static/app-v021009-bba91c83.js
custom_components/bitcoin_stack_tracker/frontend/static/style-v021009-c577172d.css
```

`panel.py` and `index.html` already reference these final assets.

## Same-version publishing note

Because the tag `v0.21.0.9` already exists, publishing the replacement under the same semantic version requires updating/recreating the GitHub release and moving/recreating the `v0.21.0.9` tag at the new commit. HACS clients already on `0.21.0.9` may need **Redownload** because there is no version increment.
