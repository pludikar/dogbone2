Dogbone2 - using direct hole method
===

## Version: 0.3

## Description

A Fusion 360 Add-In for making dog-bone fillets.

---

**WARNING: use at your own risk.**

**The code provided is provided "as is" and with all faults. I specifically disclaim any implied warranty of merchantability or fitness for a particular use. The operation of the code provided is not warranted to be uninterrupted or error free.**

---

## Notes:

This version: 0.3  Generally works, but there may be a few lingering bugs - Needs more thorough testing

---

I've completely revamped the dogbone add-in by Casey Rogers, Patrick Rainsberry and David Liu
some of the original utilities have remained, but mostly everything else has changed.  There's probably <5% of the original remaining

The original add-in was based on creating sketches and extruding - I found using this approach to be very heavy 
on processing resources, so this version has been designed to create dogbones directly by using a hole tool. The original add-in was also breaking frequently - it didn't like joints, among other things.  So far the
the performance of this approach is day and night compared to the original version (although time will tell if this claim is true). 

## Instructions

1. Select the face(s) you want the dogbones to drop from. 
2. Specify a tool diameter and a radial offset.

The add-in will then create a dogbone with diameter equal to the tool diameter plus twice the offset (as the offset is applied to the radius) at each selected edge.  The critical dimensions are maintained in the parameters - so you can change the dimensions as and when needed.  

* The add-in will only allow you to select a single component, if there are multiple copies.  Other unrelated components can be selected as needed.  

* Once a face is selected, only faces parallel to the first face can be selected.  If you need to select a different plane, just start the add-in again.

## To do:

1. an error message will sometimes appear at the end - mostly this is caused by an inconsistency either in F360 or this add-in.  However, Dog bones will generally appear correctly
2. Occasionally dogbones do not get created correctly - this appears to be a bug in F360.  Editing the offending hole(s), and changing the extents from 'To' to 'distance will usually cure this, but the holes will not longer be fully parametric!
3. ... who knows

## License

Samples are licensed under the terms of the [MIT License](http://opensource.org/licenses/MIT). Please see the [LICENSE](LICENSE) file for full details.

## Author

Peter Ludikar
