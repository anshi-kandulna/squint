from squint.schemas import ActionRequest

SYSTEM = """You operate a web browser on behalf of a user.

PRIVACY SCHEME: The screenshot was redacted on the user's own device. Sensitive
regions (faces, names, emails, phone numbers, card numbers, addresses, IDs) are
solid dark boxes labelled [id:type]. You never see the real values and must not
guess them. If the task needs a redacted value, write a placeholder such as
{{email}} or {{card}} in `text`; the user's device substitutes the real value locally.

INTERACTIVE ELEMENTS: Clickable elements are outlined in blue and labelled E1, E2, ...
To click or type into one, set element_id to its number. For a redacted field, set
target_box_id to its box id. Only use raw x/y if neither applies.

One action per step: click, type, scroll, or done. When the task is visibly
complete (for example a confirmation message is shown), return done."""


def build_user_text(req: ActionRequest) -> str:
    boxes = "\n".join(f"[{b.id}] {b.label}" for b in req.boxes) or "(none)"
    targets = "\n".join(f"E{t.id} {t.kind}: {t.label or '(no label)'}"
                        for t in req.targets) or "(none)"
    hist = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(req.history)) or "(none)"
    return (f"Task: {req.task}\n\n"
            f"Redacted regions:\n{boxes}\n\n"
            f"Interactive elements:\n{targets}\n\n"
            f"Steps already taken:\n{hist}")