# Starting memory, per step

`use-solution.sh N` copies one of these over `memory/userx.md` so every step
begins from a known file instead of whatever the last three runs left behind.

    default.md      used by every step that has no file of its own
    step6.md        used by step 6 only, if you create it
    step9.md        …and so on

The agent appends to `memory/userx.md` every time it calls `remember()`. Run
step 7 four times and the Preferences list has four identical booking lines in
it, which changes what the model reads and makes the step behave differently
each time you rehearse it. That is the problem these files solve.

## Writing a step-specific file

Copy `default.md`, change what that step needs, and name it `step<N>.md`. Two
rules worth keeping:

**Do not put anything in here that the envelope already enforces.** `default.md`
used to say *"will not travel to Tokyo"*, which was the same fact as a city
list in the code. The agent read the memory, refused the Tokyo
request on its own, and never called `purchase` — so the fence in Module 5 never
fired and the step taught nothing. Memory says what this person is like. The
envelope says what the agent may spend. Keep them apart.

**Facts here decide questions the agent would otherwise ask.** "Sam bails on
weeknights" is what lets the agent pick the Saturday show out of two Amsterdam
dates without stopping to ask you. Remove it and several steps start with a
clarifying question instead of the thing you wanted to demonstrate.
