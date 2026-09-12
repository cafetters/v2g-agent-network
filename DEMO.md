# Demo walkthrough (five minutes)

## The question

When a storm is coming, idle electric buses are rolling batteries — they
could be parked next to vulnerable neighborhoods and plugged in before the
lights go out. But the city, the transit authority, and the electric utility
are three different organizations with three different jobs. The question
this project asks: **if each organization is represented by an AI agent that
only knows its own world, can they negotiate a staging plan that's actually
good — and what does it take to trust the result?**

## The three agents

- **Emergency management** decides *who needs help most*. It ranks
  neighborhoods by social vulnerability and outage risk. It never touches a
  bus schedule or a grid diagram.
- **The transit fleet** decides *which buses can go*. It protects riders: no
  bus gets pulled off an active route, and no bus goes out below half
  charge. It doesn't decide who's vulnerable.
- **The utility** decides *what the grid can accept*. Every staging site has
  a connection limit; the utility's only authority is to say "that site fits
  one bus, not two."

They take turns — propose, allocate, validate — for up to four rounds, with
every rejection fed back as reasons. No agent sees another's private data.

## The five failures, and the one fix pattern

Every failure we found was an agent breaking a rule it had been told —
or had itself stated. In order of discovery:

1. Out of buses, the fleet agent **invented buses that don't exist** and
   assigned real ones to two places at once, rather than admit it couldn't
   cover every zone.
2. The utility **approved a plan containing a double-booking** it had
   caught and rejected just one round earlier.
3. The fleet agent **broke its own output format**, answering with loose
   text where its contract required structured data.
4. The utility **contradicted its own analysis** — writing "no violation
   found" in its reasoning while stamping the plan rejected — and once a
   phantom entry used a neighborhood's name as a bus ID.
5. Under pressure in the heat wave, the fleet agent **pulled a bus off an
   active route** — violating the one rule it recited in every round.

The fix was the same every time: **move the check from the model into the
environment.** Duplicates and phantom entries are now stripped by code,
output formats are enforced by the platform, the approve/reject decision is
computed from the actual numbers, and stranded service is measured by a
score. The agents still do all the judgment — ranking, trading off,
objecting — but no rule that can be checked in code is left to a model's
self-discipline.

## What the experiments showed

We scored every plan the same four ways: how many at-risk residents are
covered, how much energy each gets, how fairly energy is spread, and whether
bus service was sacrificed.

- **Order of speech is a policy choice.** When emergency management proposes
  first, plans go deep: fewer neighborhoods, more energy per person, most of
  it in the most vulnerable places. When the fleet proposes first, plans go
  broad: about 25% more residents covered, spread almost twice as evenly,
  but thinner everywhere and less targeted at the worst-off.
- **Backtested against last winter's three real Boston storms** (built from
  NOAA storm records, news outage reports, and real census vulnerability
  data), either ordering would have pre-positioned roughly seven hours of
  backup power in East Boston — the one neighborhood with documented
  outages — before the January storm hit. In February's regionwide
  blackout, breadth won: the fleet-first ordering covered 425 more
  critical residents on identical energy.
- **But when buses were scarce** — the December windstorm, half the fleet
  out on routes — fleet-first staged its few buses in the wrong places and
  covered **zero** of the neighborhoods that actually lost power, in every
  single run. The vulnerability ranking upstream is what aims scarce
  resources correctly.
- **The heat wave showed the ceiling.** With the fleet in full daytime
  service, two idle buses gave heat-critical residents a third of a
  kilowatt-hour each — an order of magnitude too little. Staging helps at
  the margin; it is not a grid.

One page deeper on any of this: the README, where every number traces to a
source file.
