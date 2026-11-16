"""Hammer hooks for this workspace. You (the agent) may edit this file.

Hooks inject or change steps in the tool flows. Each list holds HammerTool hook
actions; the loop's driver (loop/agent_driver.py) passes them to Hammer.

  HammerTool.make_pre_insertion_hook("step", fn)   run fn before an existing step
  HammerTool.make_post_insertion_hook("step", fn)  run fn after an existing step
  HammerTool.make_replacement_hook("step", fn)     replace a step with fn
  HammerTool.make_removal_hook("step")             drop a step

A hook function takes the tool and returns True; it usually appends Tcl.
Hammer checks the signature: it MUST be annotated exactly `(x: HammerTool) -> bool`.

  def my_route_layers(x: HammerTool) -> bool:
      x.append("set_db route_design_top_routing_layer 5")
      return True

To keep Tcl in its own file, put it in tcl/ and read it with a RELATIVE path:
      x.append(open(os.path.join(os.path.dirname(__file__), "tcl", "foo.tcl")).read())

Step names are the methods listed in each tool plugin's `steps` property, e.g.
hammer/par/innovus/__init__.py (init_design, floorplan_design, place_bumps,
place_tap_cells, power_straps, place_pins, place_opt_design, clock_tree,
add_fillers, route_design, opt_design, write_regs, write_design ...).
"""
import os  # noqa: F401  (handy for reading tcl/ files)

from hammer.vlsi import HammerTool

SYN_HOOKS = []

PAR_HOOKS = [
    # Same as Hammer's e2e example-driver used for the baseline: GCD has no bumps.
    HammerTool.make_removal_hook("place_bumps"),
]

DRC_HOOKS = []
LVS_HOOKS = []
SIM_HOOKS = []
