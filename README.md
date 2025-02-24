# Ben Fleis - Monumental Take Home - 2025-02-24

## Brief Design Notes

(See also: `notes/*` for my on-the-fly thoughts and notes.)

### Outcomes & Rough Approach
- Since no specific data given, assume robot moves (side-side or up-down) orders of magnitude slower, thus optimize for outcome metric: bricks / robot movement
- We have perfect bricks and entirely knowable desired outcome. Thus consider 2 stages: design and build as two separate phases. (This is later hinted in instructions.)
- Design for non-bonus is fixed (or at least trivially generated), begin with static pre-planned map
- Build will be frontier based, with a sort/filter priority based on height, and a look-ahead dependency indicating whether laying this brick enables other bricks to be laid without a robot movement. (Brick requiring robot movement remain in the frontier but sorted to end.)
- For given problem it appears ideal is a single (backwards) C shape, lower-left, lower-middle, lower-right, upper-right, upper-middle, upper-left; 4 strides, 1 lifts

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



