# Smart Notes implementation design

Binding scope: the owner's complete implementation request, 25 October 2026.
Extend existing independent ANVAYA JSON notes with additive sections; never split or delete legacy body. Existing body is exposed as an independently editable virtual Original Content section. Explicit section APIs use optimistic versions and the same store lock. Section bodies render on demand using the existing sanitized renderer. Each section has stable identity; attachments use the existing media store, bound by optional section_id. Main-note edits preserve sections/media. Move transfers metadata and blobs under the store lock with rollback, or is withheld if safety cannot be proved.

Reuse PR47 exact head ab73e63 as baseline, preserving PR44 Android navigation optimization. Other unmerged branches remain unchanged. Universal attachments extend its streamed, bounded, signature-checked, read-only external-open store. No internal audio/video player. Obsidian remains optional with honest Android snapshot fallback if no certified SAF vault bridge exists. Android owns light native animated startup, reduced motion, readiness transition. Current shared coordinator PR53 is unmerged; use available V1 focused selection and report compatibility rather than replacing workflows wholesale.

Alternatives: splitting paragraphs risks losing meaning and references; separate unrelated documents defeats hierarchy. Additive sections avoid both. A live Android SAF mirror requires installed permission/lifecycle verification; bounded explicit snapshot import is a truthful supported fallback.

Validation: service/repository races, legacy preservation, route CSRF/optimistic conflict, actual Chromium 360/390/430 accordions/search/edit/attachments, existing note/media/Obsidian regression and wider suite. Native SDK/installed verification reported independently; no build claim without artifact.
