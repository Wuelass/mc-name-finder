# Third-party notices

The MIT license covers this project's code. It does not relicense dependencies, dictionaries, trademarks or corpus-derived data.

## wordfreq

Built-in word discovery uses **wordfreq by Robyn Speer**, distributed as a dependency rather than copied into this repository.

- Upstream: https://github.com/rspeer/wordfreq
- Code license: Apache License 2.0.
- Corpus data: Creative Commons Attribution-ShareAlike 4.0; see the [upstream licensing section](https://github.com/rspeer/wordfreq#license) for source-specific terms and the complete credits.
- SUBTLEX: freely available data by Marc Brysbaert and collaborators; retain this attribution.
- Other upstream sources include Google Books Ngrams, Leeds Internet Corpus, Wikipedia, ParaCrawl and OpenSubtitles. Consult upstream for full citations.
- Citation: Robyn Speer (2022), *rspeer/wordfreq: v3.0 (v3.0.2)*, https://doi.org/10.5281/zenodo.7199437.

This tool uses the library to select and normalize names, then adds Minecraft API observations. It is not a general-purpose export of the frequency database. Reports include original words, normalized forms, language and check results; the JSON checkpoint also retains a ranking score for resumption. These transformations do not remove upstream data obligations.

Wordfreq-derived data remains subject to [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Keep generated JSON attribution and `NOTICE.txt` with shared reports and text lists, credit the upstream sources, indicate normalization/filtering changes, and preserve applicable share-alike terms. Do not publish the entire wordfreq database as CSV. Results and dictionaries are ignored by Git by default.

## Other dependencies

Requests (Apache-2.0), python-dotenv (BSD-3-Clause), Rich (MIT), and development dependencies retain their respective upstream licenses. Python packaging installs their distributions with their own notices.

## Authentication helper

Microsoft device-code authentication uses [prismarine-auth by PrismarineJS](https://github.com/PrismarineJS/prismarine-auth), version 3.1.1, under the MIT license. The dependency and its transitive dependencies are installed into local application data using the bundled npm lockfile; their distributions retain their notices. The bridge follows the upstream Java-token example and uses its Minecraft Nintendo Switch client title. This project does not own that Microsoft client registration.

## Minecraft

Minecraft and related marks belong to their respective owners. This independent tool communicates with Minecraft Services; it is not endorsed by Mojang or Microsoft.
