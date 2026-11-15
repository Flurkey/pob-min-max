# Build fixtures

`scion-baseline.xml` was exported by the pinned Path of Building engine (dev `e5917f81`, tree 3.30), not written by hand.

It is a level 1 Scion on the 3.30 tree with only the class-start node allocated. The file contains `<PlayerStat stat="Life" value="60"/>`. That tag is a cache written by PoB at save time. Tests import the file, including a copy whose Life cache has been forged, and require the engine to calculate Life itself.
