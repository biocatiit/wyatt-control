# wyatt-control
Python based control of Wyatt instruments using the ASTRA API

Requires 64 bit python to run

Requires a version of ASTRA with the Automation API license.

Requires at least ASTRA 8.1.1

Python dependencies:

* pythonnet
* packaging

## Usage:

ASTRA must be closed before you start the python control. It will open ASTRA on it's own. While the python control is running, You should not interact with ASTRA by any means besides the python control, otherwise you may lock up ASTRA.

```python
# Create the WyattControl object. This starts ASTRA.
wc = WyattControl()

# Create a new experiment
exp_id, exp = wc.create_experiment('//dbf/Method Builder/BioCAT/SEC_MALS_SAXS_20260314',
    run_time=3, name='Sample1', descrip='My sample', flow_rate=0.6,
    inj_vol=0.3, conc=0.12, dn_dc=0.18, uv_ext=1, a2=1, auto_baseline=True,
    auto_peaks=True, use_inst_cal=True)

# Validate the experiment
valid, errors = wc.validate_experiment(exp_id)

# Start the experiment and wait for data collection to start (note: if
# wait_for_collection is false start_experiment won't block and you can do
# other things while it runs)
success = wc.start_experiment(exp_id, wait_for_collection=True)

# Wait for the experiment to end
wc.wait_for_exp_end()

# Save the experiment and results and close the experiment
wc.save_experiment(exp_id, 'C:/Users/biocat/Documents/MALS/test/test')
wc.save_results(exp_id, 'C:/Users/biocat/Documents/MALS/test/test_results')
wc.close_experiment(exp_id)

# Close the WyattControl. This closes ASTRA.
wc.close()
```

Documentation of available classes and methods is done via sphinx compatible docstrings and can be built in the docs folder.
