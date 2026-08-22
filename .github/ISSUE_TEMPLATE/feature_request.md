---
name: Feature request
about: Suggest an improvement
labels: enhancement
---

**The problem you are trying to solve**

**What you have tried**

**Would this work as a filter plugin?** Most new filters belong in a plugin
rather than in core — see docs/EXTENDING.md. Core filters need to be general
across corpora and languages, dependency-light, and cheap per document.

**Does it affect build hashes?** If it changes what a build keeps, it must
also change the filter config sha. Say how you would handle that.
