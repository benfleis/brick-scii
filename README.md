# Ben Fleis - Monumental Take Home - 2025-02-24

## tl;dr - Watch It Go

Need to have python 3.13 - I used 1 feature there but will tweak it later to be more broadly compatible. (Didn't realize it was a new-ish feature.)

```
    pip install colored pytest
    pytest -vv brick-scii.py
    ./brick-scii.py | less -y 35 -z 35
```

Using less allows Space/f to go forward 1 step, and b to go backward.

## Summary

- Most fun take home I've ever had, certainly only one I made videos to share :)
- Simplest Approach: Design + Plan/Execute are separate phases. Treat as layout with separate state machine.
- Optimizing Strides is key, current solution is decent, will add more after first submit.
- Bonus 1 addressed with English Cross; adapted outputs to work better with head joint display
- Perhaps best to start at `State` class for top-level reading.

## Brief Design Notes - Written BEFORE Coding

### Outcomes & Rough Approach

- Since no specific data given, assume robot moves (side-side or up-down) orders of magnitude slower, thus optimize for outcome metric: bricks / robot movement
- We have perfect bricks and entirely knowable desired outcome. Thus consider 2 stages: design and build as two separate phases. (This is later hinted in instructions.)
- Design for non-bonus is fixed (or at least trivially generated), begin with static pre-planned map
- Build will be frontier based, with a sort/filter priority based on height, and a look-ahead dependency indicating whether laying this brick enables other bricks to be laid without a robot movement. (Brick requiring robot movement remain in the frontier but sorted to end.)

### Representations

- Wall: finished wall dimensions
- Layout: set of unique brick locations, marked with number and corners; could in second pass determine dependencies (eg, that a brick can only be accessed if all bricks underneath it are already laid).
- Robot:
    - reach bounding box: robot has a specific reach, need to represent that as primitive in order to sort/filter brick reachability
    - movement bounding box: robot can move side-side and up-down with specific limits (in practice KISS, match reach box; real solution might account for per-brick overlaps and be more specific)
- No need to represent head/bed joints outside of design phase AFAICT

State is a state snapshot containing robot location + brick layout + brick states
Act will be a state transformer based on available actions that returns next state.

### Actions

Once design is complete and we have a layout available actions:
- lay brick in location X, Y
- move robot to location X, Y

### Interface

Let's display ASCII:
- light white for locked bricks (missing supporting brick)
- red+bold for laid bricks
- green for eligible frontier (eligible = unlocked + reachable by robot)
- yellow for ineligible (unlocked + unreachable by robot)


## Disorganized Notes - DURING/AFTER Coding

### Solution Notes

- Stride planning is the magic sauce. I tried 2.5 versions. Where I ended has some obvious improvement possibilities, I assume we'll discuss.

- Approach is currently entirely Cartesian, should allow arbitrary elements/brick sizes, but not tested. Did manual testing with various wall sizes, layouts and robot reaches.

- Testing is adhoc and minimal - specific unit tests for things that had bugs and needed a specific test/fix approach. The tests themselves are incomplete, happy to discuss how I'd approach IRL.

- I have done some testing with Bonus 1, it partially works. Need to fix a bug in raise functionality to finish generalized.

### Code Notes

- Approach - hackathon + 1st pass refinement.

- I began with a string based rep to keep it simple. I got partial functionality pretty quickly here, but hit-the-wall (pun intended!) at my first attempt to properly calculate "support" dependencies. A simple-overzealous approximation with strings is simply every index is supported by its immediate underneath+2 siblings. This is enough to make progress and build walls. After quickly confirming this, I moved on from the string rep, and used strings as human-friendly layout spec, and internally converted to using `PositionedBits`. (Bit = Item.)

- This problem wants to be solved in a functional/immutable way, as a series of states and actions, ffwd/rewind etc. As much as reasonable in python I approached this way. But I didn't get to ffwd/rewind. (Not implying that it's required for that functionality, but is a natural approach IMHO.)

- Leveraged python types where reasonable to avoid obvious mistakes, but avoid zealotry. Win for disambiguating e.g. Cartesian Coordinates from Logical Positions, etc.

- Prefer named constants; they're easy to maintain and avoid face-palm typos.

- Single file python. IRL would split things up, but no need for this.

## Known / Anticipated Warts

- Stride planning is nice but imperfect. Handing in to get the ball rolling but it's the next thing I'll play with. Lowest frontier is a good starting point. My instinct says that greedy selecting the max number of unblocked bricks in 1 position is probably "good enough". I imagine the "upward" pyramid from a brick as projected dependency-set, trimmed by the robot-boundingbox

- I treated head joints as first-class bits, but did not prevent them from being installed without neighboring bricks. TODO!

- Raise function broken for non-test walls.
