# Changelog
All notable changes to this project will be documented in this file.

## v[major.minor.patch] [dd/mm/yyyy]
### Added
None.

### Changed
None.

### Deprecated
None.

### Removed
None.

### Security
None.

### Fixed
None.

## v0.1.3 [10/11/2023]
### Fixed
- Fixed calculation of "Rf" to evaluate happen when qc not equal to 0 or None and fs not equal to None if Rf is missing in CPT.

## v0.1.2 [16/10/2023]
### Added
None.

### Changed
- updated bro version to 0.2.9 to fix breaking changes from REST API.

### Deprecated
None.

### Removed
None.

### Security
None.

### Fixed
None.

## v0.1.1 [10/10/2023]
### Changed
- updated bro version to 0.2.8 to fix other retrieved params from BRO REST API
- updated VIKTOR SDK version to v14.6.0

## v0.1.0 [04/10/2023]
### Changed
- updated bro version to 0.2.7 to fix returned XMLS from BRO REST API

## v0.0.6-beta [17/05/2023]
### Added
- Added date of which CPT was performed to MapLabel of CPT
- updated bro version to 0.2.6

## v0.0.5-beta [15/04/2023]
### Fixed
- Fixed breaking CPT plot on missing "date" key in researchReportDate

## v0.0.3-beta [07/04/2023]
### Added
- Added some error handling on cpt characteristic retrieval
- Added pictures to README.md

### Changed
- Updated bro version to 0.2.3


## v0.0.2-beta [31/03/2023]
### Added
- (#7) Added outline of NL to MapView
- (#7) Added MapLegend

### Changed
- (#7) Implemented the bro package to retrieve cpts.
- (#7) Updated README.md
- (#6) Allow CPTs that miss 'depth' information to be classified with the Robertson method, using 'penetrationLength' as depth.
- (#6) Updated descriptive text in parametrization.

### Deprecated
None.

### Removed
None.

### Security
None.

### Fixed
None.


## v0.0.1-beta [10/03/2023]
### Added
- (#1) Added Parametrization to define polygons
- (#1) Added MapView to show defined Polygon and retrieved CPTs from BRO in step 1
- (#1) Added Retrieve CPTs button in step 1 to check which CPTs are in selected area
- (#1) Added MapSelectInteraction in Step 2 to select CPTs of interest
- (#1) Added Robertson Classification method
- (#1) Added Visualisation of max 10. classified CPTs with Robertson method
- (#1) Added DownloadButtons to retrieve CPTs in XML format from the BRO

### Changed

### Deprecated
None.

### Removed
None.

### Security
None.

### Fixed
None.
