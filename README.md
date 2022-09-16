Scribe Edge addin for fusion 360
===

## Version: 2.0

* **Windows users:**

   * You can download a self extracting file [here](https://github.com/DVE2000/Dogbone/releases/download/v2.0/winsetup_Dogbone_v2_0.exe) 

* **Mac users:** 

   * If you installed F360 directly from AD - download self extracting file [here](https://github.com/DVE2000/Dogbone/releases/download/v2.0/macSetup_AD_dogbone_v2_0.pkg)

   * If you installed F360 from Apple App Store - download self extracting file [here](https://github.com/DVE2000/Dogbone/releases/download/v2.0/macSetup_appstore_dogbone_v2_0.pkg)

   If you're having problems due to Apple Security, instead of clicking in the Downloads Dock icon Folder or Stack, click "Open in Finder" and then right-click the package and select "Open". You'll be able to install it then.



zip and tar files available (for both Mac and Windows) [here](https://github.com/DVE2000/Dogbone/releases)

---

## Description
Creates a scribed edge from a CSV file.  Allows an edge to be contoured to eg a wall that isn't straight| 
-----------------------------|

**WARNING: use at your own risk.**

**The code provided is provided "as is" and with all faults. We specifically disclaim any implied warranty of merchantability or fitness for a particular use. The operation of the code provided is not warranted to be uninterrupted or error free.**

---

## Installation

See [How to install sample Add-Ins and Scripts]()

## Instructions
**Note that you can hover your cursor over any Dogbone dialog item and you will get an explanatory popup in Fusion360.**

1. Select the face you want associated with the scribed edge.
2. Select a reference edge - ie the edge from which measurement intervals are taken - eg  0", 2", 4" etc.
3. Select the offset edge - ie the edge that will be scribed.
4. Select the CSV file that contains columns headed "dist" and "offset"

The add-in will then create the specified scribed edge

## License

Samples are licensed under the terms of the [MIT License](http://opensource.org/licenses/MIT). Please see the [LICENSE](LICENSE) file for full details.

## Authors
Peter Ludikar (pludikar), Gary Singer (DVE2000), Casey Rogers (casycrogers)
- Original version by Casey Rogers: https://github.com/caseycrogers/Dogbone/tree/cbe8f2c95317ae7eded43fee384171a492c6900e
- Original version Modified by Patrick Rainsberry (Autodesk Fusion 360 Business Development)
- Original version Modified by David Liu (http://github.com/iceboundflame/)

