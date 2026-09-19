
# UI/UX/Styling

* Stick to bootstrap 5 UI components as much as possible.

* Use existing helper classes if needed.

* Avoid custom classes or inline styles.

# Typing

* Use pydantic if handling JSON on the server side.

# Interactivity / Client-side scripting

* Never ever create new javascript.

* Try to stick to HTMX with partials where possible

* You must use hyperscript to implement client-side scripting if that is needed.

Revisit your approach if this becomes clumsy, the overall HATEOAS approach
needs to be properly respect to avoid crazy local solutions.

# Chameleon / Page Templates

* Prefer direct attributes of tal:attributes:

  Good: attribute="${expression}"
  Bad:  tal:attrs="attribute python:expression"

  You might need to use tal:attrs if the attribute itself might be optional if expression evaluates to `None`.
