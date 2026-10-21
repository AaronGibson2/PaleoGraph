# PaleoGraph visual identity

The branching **P** connects a classification branch to two short geological strata. Its open bowl and single evidence point work as a compact mark, without illustrating a particular organism or implying a phylogenetic relationship. Evergreen ink, mineral paper and the existing editorial wordmark connect it to the field-atlas interface.

- [Primary logo](../apps/web/public/brand/paleograph-logo.svg): mark and Georgia wordmark; text remains editable and depends on a serif font.
- [Standalone mark](../apps/web/public/brand/paleograph-mark.svg): transparent, original vector geometry.
- The shared `PaleoGraphBrand` component supplies the Home wordmark and compact workspace rail treatment. Parent links provide accessible names; the SVG is decorative.
- [Browser/app mark](../apps/web/app/icon.svg): a simplified light mark on an evergreen rounded square, served through Next's icon metadata.

Use the full signature where space permits and the compact mark in navigation. Keep the silhouette clear at small sizes; avoid additional animation or repeated logos in scientific records.

## Decorative animal coverage

The renderer has 27 reusable body forms: the existing 14 transparent raster masks and 13 original filled vector silhouettes. New forms cover rays, salamanders, lizards, carnivorans, ground sloths, glyptodonts, eels, flatfishes, small insectivores, marsupials, angel sharks, pinnipeds and cetaceans. They share the existing single-ink mask treatment and fit dense rows without new image frameworks or network services.

Membership is explicit: reviewed UFVP source UUIDs and namespaced retained PBDB identifiers in `expanded-rules.ts`. Labels document the review; runtime resolution never infers membership from a name. The taxonomy projection supplies membership nearest first, so a broad neutral Reptilia node cannot hide a supported crocodilian or turtle. Additional specific forms override broader ancestors. Unknown and intentionally broad or unsuitable groups remain neutral.

These are orientation aids, not specimen photographs, exact species reconstructions, morphological evidence or proof of evolutionary relationships. Detailed source identities and uncertainty stay in the adjacent text. Image failures retain a neutral fallback. Hover is unnecessary for recognition, and reduced-motion behavior is unchanged.
