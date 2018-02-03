Dogbone2
===
v: 0.3
Author-Peter Ludikar
Description
===
A Fusion 360 Add-In for making dog-bone fillets.

Notes:
===
This version: 0.3  Generally works, but may be a few lingering bugs - Needs more thorough testing
'''
**WARNING: use at your own risk.** 
The code provided is provided "as is" and with all faults. I specifically disclaim any implied warranty of merchantability or fitness for a particular use. The operation of the code provided is not warranted to be uninterrupted or error free.'''

I've completely revamped the dogbone add-in by Casey Rogers, Patrick Rainsberry and David Liu
some of the original utilities have remained, but mostly everything else has changed.

The original add-in was based on creating points and extruding - I found using sketches and extrusion to be very heavy 
on processing resources, so this version has been designed to create dogbones directly by using a hole tool. The add-in was also breaking frequently - it didn't like joints, among other things.  So far the
the performance of this approach is day and night compared to the original version. 

Select the face you want the dogbones to drop from. Specify a tool diameter and a radial offset.
The add-in will then create a dogbone with diameter equal to the tool diameter plus twice the offset (as the offset is applied to the radius) at each selected edge.  The critical dimensions are maintained in the parameters - so you can change the dimensions as and when needed.  

The add-in will only allow you to select a single component, if there are multiple copies.  Other unrelated components can be selected as needed.  Once a face is selected, only faces parallel to the first face can be selected.  If you need to select a different plane, just start the add-in again.


To do:
---
1. an error message will sometimes appear at the end - mostly this is caused by an inconsistency either in F360 or this add-in.  However, Dog bones will generally appear correctly
2. Occasionally dogbones do not get created correctly - this appears to be a bug in F360.  Editing the offending hole(s), and changing the extents from 'To' to 'distance will usually cure this, but the holes will not longer be fully parametric!
3. ... who knows
