
# DONE





* [x] cleanup unused javascript code, try to thin out as much as possible, convert to simple htmx/hyperscript

  * [ ] convert (and correct) help overlay into htmx/hyperscript

  * [ ] undo

  * [ ] error

  * [ ] protocol and run keyboard navigation and control

  * [ ] images

  * [ ] are sortables still needed?

  * [ ] ideally menage.js can go away after this and no plain javascript has been added






## Clean up and unify adding/editing

- the input box is different for new tasks, protocols and protocol items

- the inline editing with contentEditable seems fragile

- the pickers are weird and different between adding and editing

- there's at least two types of widgets: single value and list

* create a single form panel that can be used for all situations: new,

* [x] simple widget for note and title

* [x] allow saving again

* [x] make simple widgets from htmx partials that are bound to the
      corresponding visible input field and get updated when
      typing there and allow picking / previewing as modules

  * [x] due date

  * [x] repeat

  * [x] remove parser from client side

* [x] widgets for multi-items

  * [x] tags

    * [x] backspace delete previous tags

    * [x] save on enter with no

  * [x] assignees

  * [x] links

  * [x] attachments

    * [x] proper layout

    * [x] better drop zone



    * [x] remove the 'add' button, 'enter' on desktop should be enough, on mobile there should be a keyboard action that can trigger submit without an explicit button in the UI

    * [x] tag-gruppen ein und ausklappen


  * [x] todos anlegen

    * [x] tags vergeben

  * [x] mobile view

    * [x] swipe right für "Erledigt"
      * [x] undo

  * [x] "jetzt nicht"
    * [x] icon für "später" (oder skip? oder besserer begriff?)
    * [x] menu um geskippte wieder zurückzuholen

  * [x] hierarchische tags
    * [x] indentation

  * [x] tags als besserer datentyp in postgres?

      * [x] there's a red flash when postponing, get rid of that (i think it's a global "htmx is busy")
    * [x] dashes should be acceptable part of tags (everything except whitespace?)
    * [x] undo the separate "single action" and "bulk action" mechanisms for updating the list. always update the list.
    * [x] the title "todos" is not useful on mobile, turn the head menu into a proper burger menu on mobile (show only the title and allow unfolding the navigation), provide a more consistent approach to rendering the function level navigation (maybe a separate + icon, the "done items" and the "postponed" items). on desktop the header navigation should not be hidden
    * [x] toasts should be a bit more visible, use more visible background color, maybe a bit bigger and ensure proper font contrast, disappear, let it stay a bit longer, the toast should also should have a more 'floating' appearance and not be stuck within the content.


  * [x] switch testing to postgresql

    * [x] indentation ist schon wieder verrutscht, expand sollte auf gleicher einrückung sein wie das eingabefeld


      * [x] editing text (and tags) -> load into text field and then update

    * [x] allow adding something new with existing tags into the tree
    * [x] allow adding multiple things with the same tag -> keep tag for next
    * [x] add (clear) button to the entry field to get rid of the
    * [x] autocomplete tags while typing

    * [x] select the checkbox when clicking the item
    * [x] better homepage, don't start with recipes? maybe start with todos?


     * [x] only show tags for editing when the editing text field is focused

## einkaufsliste (see weekly planner)

* [x] remove RTM integration, send to the internal TODO list
* [x] create a sqlalchemy migration to update the "shopping:" tags into "einkaufen:"
* [x] rezepte (und jeweilige rezeptmenge) an einkaufslisten items als detailnotiz dranschreiben
* [x] rezepte markieren wenn sie nicht auf die einkaufsliste sollen
* [x] rezeptmenge nur wenn es mehr als 1 rezept ist

* [x] shopping list tags (obst, kühlung, ...) umschreiben auf einkaufen:supermarkt:...

* [x] indicators for "done" and "postpone" when swiping are stuck within the LI

* [x] add claude.md

* [x] fix public transport



* user management


  * [x] add basic user management (add/remove/password recovery via email (drop via local sendmail))
  * [x] add permissions for managing users (use a proper pyramid authorization implementation)

  - [x] devenv mailhog?

  - [x] secure defaults: default acl / permissions that ensure that views without
    explicit permission are denied by default (to basically everyone)

  - [x] setup - generate a token on startup and print in the log with a
    url to visit, only allow using the setup with this token
    and then destroy the token and prohibit access to the setup views after,
    when redirecting to the setup, then don't fill in the token automatically but
    ask the user for it

    - [x] instead of using the development server and database, add a second test server and database to the devenv and run the tests against those, the database should be proper prepared/cleaned with test-scoped fixtures, so we can expect clean state instead of deltas in each test and also so i can interact with the development server as a user. don't require environment variables to configure the tests, e.g. for playwright tests, put those in a fixture that ensures the proper values.

  - [x] does the password reset link have an expiry?

  - [x] consider the safety of this: is all of this necessary for development? add comments to those line for the recommended production settings

    session.w = true
    session.secure = false
    session.samesite = Lax


  * [x] adding new ingredients is broken - write a test

  * [x] shopping cart toggle has blue underline


  * [x] weekly planner use card titles as headings, simplify the floating layout (use flex grid?)


* [x] sign out alignment ist broken


* [x] when focusing the text field and no tag pills are there, i don't want the content to slip downwards for empty space

* [x] switch to bootstrap

  * [x] consistent use of browser window width: give all content the a bit of the same margin or padding, ensure the headlines stay  aligned with the content, ensure some visual distinction between the page content and the background (border? background color?)

  * [x] consistent placement of save/abort buttons

* [x] relative time parsing (auch auf deutsch)

* [x] echte deadline, echtes postpone


* [x] repeat "every" und "repeat after"

* [x] protocol items

    * [x] allow selecting tags with the ui helper and pills

    * [x] allow adding notes, suggest an inline marker (like #, \*, ... )

    * [x] the line hight of the wrapper for the text field is too high (too much space below it)

    * [x]  use a proper icon and button for the delete [x] and provide an undo

    * [x] only display the save button when there are changes on the item

    * [x] when saving an item, i don't want the page to scroll up

    * [x] saving an item loses the changes in all other items

    * [x] don't add "run protocol" to the todo list run,

    * [x] edit template should be "edit protocol"


* [x] "every second friday" doesn't parse

* [x] how does the first instance of a protocol repetition chain start?


* [x] align checkbox in todo (And in protocol runs) with note properly on the line of the title of the todo, not vertically centered, maybe use a better flexbox approach to combine the checkbox with the title the indentation of the notes?

* [x] Protocols

  * [x] sollten auch listen von todos sein, aber mit einem anderen marker und separatem menü? und dem feature "use checklist" to transfer them into actual todos

  * [x] abarbeiten ist im prinzip die entscheidung: einmal diese liste durchgehen und jeweils ja/nein sagen, damit man es abgearbeitet hat


* [x] in the edit field for todos: keep the pills in order, intermingled with the entered text and use an assemblage of divs that carry contenteditable, make sure i can navigate with the cursor natively around and through the pills (triggering the pickers when the cursor enters them)



* [x] scheduled items need to be able to be edited properly while in the schedule (re-use the editing widget from the main page)

* [x] typing ^ in the field should immediately enable a preview with similar styling as the shift-p postpone picker and pull it into a separate pill (that is editable), the default suggestions should be today, tomorrow, the next 3 days after that as weekdays, 1 week, no date. the picker should in both cases (complex postpone and ^schedule editing pill) show a row of choices and a month-date picker below that.

* [x] the "h" or "?" cheatsheet doesn't work. also, it should work on all todo views (including the scheduled and done views)

* [x] editing something with a repetition needs a pill similar to editing the due date

* [x] the repetion and history is not shown in the schedule view

* [x] collapsed tag group titles are unreadable, too little contrast (gray on gray)

* [x] clean up protocols feature

    * [x] new protocol button breaks over multiple lines

    * [x] show protocol link indicator in schedule and archive

    * [x] better "new protocol" ui: don't require title to create it initially

    * [x] create / regenerate the first instance of a protocol repetition immediately after saving the protocol

    * [x] completing a protocol run doesn't immediately spawn the next todo for that protocol in the schedule, but it should

    * [x] if the title of a protocol changes, update non-archived/non-completed linked todos


* [x] multi-player

  * [x] wer sieht was wann?

  * [x] wie vergibt man tasks an gruppen/personen?

  * [x] wie integriert sich das mit protokollen?


## multiplayer

let's add proper "multiplayer" support

* add a teams function that is basically a set of users
    * users in a team can be assignees or supervisors: assignees will receive items in the list as

* usernames and team names must from a unique set  (principals)

* allow adressing one or more principals with @ when adding a todo item
* allow adressing one or more principals with @ when adding a protocol
* allow addressing one or more principals with @ in protocol items

* keep track of the owner of a task who created an item

* everybody is only allowed to see the tasks they are the owner of, have been assigned it directly or are a member of an assigned group (as assignee or supervisor))

* users can enable toggles in the current task view and schedule view to allow

  - showing only personal tasks, not the ones they got delegated
  - showing only tasks that are delegated to others
  - showing all tasks they are responsible for (are the owner and have not delegated it, or tasks that have been delegated/assigned directly or as an assignee in a group they are a member of)
  - show only tasks they got via delegation

* include showing assignees (not owners) via @ in the right side of the todo list entry


# Refining

- [x] delegated tasks to someone via group is not showing up in their personal list where they are an assignee in the group
- [x] protocols are visible to everyone, not just the owner
- [x] i can't add assignees to the protocol itself
- [x] sums in on hold/scheduled/done do not respect visibility rules
- [x] a protocol assigned to a team is not visible to the assignees of that team


## clean up the menu structure, add a second level (within the white header):

* [x] Victuals (sub menus: meal planner, recipes and ingriedents)
* [x] Tasks (sub menus: active, on hold, scheduled, done, protocols)
* [x] Operations (sub menus: crew, departments, operations (subsuming access to the dashboard and running the recurrence sweep into multiple cards on the same page)
* [x] replace "sign out" with "Log off"
* [x] pick reasonable bootstrap icons for those main menu items, highlight the currently selected one
* [x] put the sub menus in the white area, use proper highlighting for active menus and submenus according to bootstrap styles, consider the bootstrap options to put submenus there and combine with the action buttons
* [x] put the "Archive protocol" link as a button into the action area


* [x] rip out basic auth on server

* [x] archive protocol should be an action button

* [x] changing the repetition rule of a protocol should cancel future instances and rerun the generation


I want to create a feature that extends on the TODO list in multiple axes: checklists and scheduling/repetition.

1. Scheduling

TODO list items should have a scheduled date (no time, just the date) attached to them (when hovering/selecting), press 'd' to select the scheduled
date. Present a little calendar picker, allow entering ISO dates or humanized days like 'wednesday', 'next week', 'in 7 days', "a week", "a month", "next march" or "march 2026", .... Ensure proper factoring of parsing this and testing this conversion. When entering, a human

Allow adding a due date when adding a todo item using the '^' marker, similar to adding tags with the '#".

When entering a due date, provide a visual cue to what the parser determines for the final date (e.g. when typing and detecting "1 week" show the date in a week in some preview form)

Consider how to allow hiding them from the actual current todo list but also keeping them reachable for review and editing.

Display the due date in the todo list in a reasonable way that isn't too prominent but findable when needed, highlight things that are due to day and more prominently when overdue.

Allow postponing seleted/hovering items by 1 day by pressing 'shift-p'. Provide a dropdown selection for postponing by a number of pre-defined intervals (1/2/3 days, 1 week, 2 weeks, 1 month). If pressing 'shift-p' on an overdue item, set it's due date to today.

2. Repetition

We also want TODOs to repeat on regular intervals. Two types of intervals: "after" and "every".

The "after" interval uses the attached rule for the item to be scheduled based on the day it was completed.

The "every" interval fires according to it's rule independently when or whether the previous item was completed or not. So, if something repeats "every wednesday" and we complete it on friday, the next time it should also start on wednesday. However, if something repeats "after a week" then if it was completed on friday it becomes due again the next friday.

When creating a repetition instance, create a new TODO item with the appropriate schedule. Clone the item that was completed, set its schedule date and keep a link between repetition instances and visualize the repetition history.

We create repeating items by creating a todo and using  '*'  as a shortcut, pick this up with a similar dropdown like the tags and suggest a number of default repetitions:  every day/week/month/year, after a day/week/month/year. Allow entering human times like ""

Use 'f' to edit the repetition rule of hovered or selected items.

3. Checklists

We have more complex things that need to be reviewed (like going through the weekly routing of checking inventory, making a weekly meal plan, checking cosmetics inventory). The list itself has a repetition and due date, so it's very much like a TODO item itself. However, it consists of multiple items that are then just checked off or sent to the todo list (mainly with a tag to e.g. indicate that this is like an ingredient that needs to be fetched from a specific store and store department).  Every checklist needs a title

We call this "checklist", but maybe there is a better name. Suggest alternatives and let me chosse before starting to implement.

We also want to be able to start working on a new checklist instance "now".

We need a place to edit them and a place to "run through" them. Each check list item will result in
it either having been done or requiring to be send to the real todo list. Each check list item carries the same data (text, tags, notes) like the todo list items
but i'm not sure whether they themselves should be checklist items. I'm wary of getting confused between editing a checklist and working through the todo list.

We need reminders to go through the check lists at some point, so that's where the overall checklist itself is a bit like todo item. Maybe a checklist could be associated with a todo item that has a repetition on it. Maybe use some UI around this to generate a TODO list item for a checklist and where the todo list item then allows accessing a checklist instance to work through. Checklist instances need to be properly shared on the server side for multiple people to access. Maybe it's also that running through the checklist creates a todo list item that is due now. Todo list items that associate checklists in the future should ensure they use a current version of the checklist when they become due.

Good UX design, proper function and unit factoring for those three items is important to me - both aesthetically and usability wise.



----- questions


1. name: lets go with "protocol". i like that this is a bit more formal and playing into a potential sci-fi/space/nasa theme.

2. separate buckets: yes

3. postponed/paused: keep both, but lets use "on hold" instead of "paused" and postpone for the planned new postpone action. use "h" for the previous "pause" action. consider a different icon for "hold". use "p" for "one day postpone" and "shift-p" for the extended choice of options

4. background jobs: yeah, lets go with the simpler lazy spawn option. as this is only needed once per day, keep track of whether we've run it already
   for the day and don't run it all the time.

5. versioning: the snapshot is taken when the run is instanciated (at spawn time)

6. Scope: lets create separate 3 steps that build on each other as you proposed. No need for branches, just take a break after each part and ask me to validate the code after you're done and then continue with the next step or let me refine and then continue when I give the go.

Also, allow starting a route directly from the todo (create an instance and associated task) view by pression "r" as a hotkey and giving an overlay palette (similar to the way palettes work with sublime text) where finding by "substring" (similar to tags) works and opening up the specific new run.

Also, provide reasonable hotkeys for items in a run and also allow the swipe-left/right mechanic. Swipe right means "nothing to do", swipe left means "put it on the todo list".

Remember to update the hotkey help dialogue.

Show me the updated plan.


- [x] rename victuals to "Food"


* [x] @familie -> christian/sarah als assignees  ... duale rollen erlauben: supervisor + assignee?

* [x] "personal" -> "My Tasks"

* [x] password recovery is broken

* [x] "protocol" -> turn the overall theme from the somewhat unwieldy "menage" to something more sci fi/space/nasa inspired?

* [x] tag autocompletion needs to include all tags from scheduled/done/on hold/... todos


* [x] allow editing the comment on todos


* [x] make dashboard accessible from normal menu?

* [x] echtes multi-player: individuelle tasks, tasks auf gemeinsamen gruppen
  @ um leute (und gruppen) anzusprechen


* [x] today/tomorrow/next week view


## support attaching pictures to todo items

 * [x] allow attaching pictures by dragging them onto a note. support multiple pictures.

 * [x] store pictures in a folder on the server that is configured in the ini file

 * [x] generate a uuid for the filename, keep the proper extension, store the uuid in the database, ignore the uploaded filename, verify the mimetypes that PIL supports

 * [x] use pillow to provide a scaled down version of images for small previews and provide an icon that indicates there are pictures, allow hovering to see a preview of all attached pictures

 * [x] allow clicking on a single picture to open a modal showing it in large size, make sure this works well on desktop and mobile, especially to leave the modal

 * [x] ship the picture through an endpoint using the todo item id and picture ID that verifies security (whether you have access to the todo item)

 * [x] pictures should receive a pill so they can be removed while editing


  * [x] make the mars background less "gasy" - this looks like it's the sun - make it look more solid, it hass less atmosphere thus more crisp on the edges, less authorization
    and more of a visible "basin/valley" structure. it should be partially shaded, the colors range from DDA582, C09086 and 432A21.

  * [x] allow setting a custom "base name" as an admin in the operations center, replace the "Happy Valley" strings in the templates with that setting



## support attaching urls to TODO items

 * [x] allow the ~ notes text to wrap (not overflow hidden) when rendering todo items

 * [x] allow attaching urls using markdown syntax []() and render them in the notes area

 * [x] support them as pills, choose an appropriate character to trigger them while editing

 * [x] also allow []() urls within notes, don't extract them, leave them in there and render them within the notes

* [x] improve the keyboard shortcut dialog

  * [x] don't respond to '?' if focus is in an input field (or contenteditable)

  * [x] you're using lots of custom styling, remove all custom styling, only use bootstrap defaults, prefer high level styles and components over low level styles.

  * [x] the colors  for key literals are bad, it's white on light grey.

  * [x] it's growing too big, use somewhat smaller font and use two columns


* make the todo list look more like a lineated sheet of paper (only thin lines between the todos), use a regular headline styling for the tag groups
* don't indent the categories and don't display them nested, keep the order, but show a full "breadcrumbs" bar for each tag group
* move the due date to the right side
* cap the width of the list on desktop to an em equivalent of 680px, use full width on mobile devices (tablets and smaller)


* [x] submenu is completely inaccessible on small mobile devices (iphone) -> can't call back paused items


## Fix assignee/owner/delegation filtering consistently over all lists

The active / paused / scheduled / all lists have inconsistent filtering of items with different owners/assignees/supervisors.
Each of them seems to implement the 'my tasks', 'delegated out', 'delegated in', and 'all' filters differently.

The rules should be:

- my tasks: the ones i need to act on
- delegated out: those i own and have assigned some team or am a supervisor on an assigned team, but don't include those where I end up being the assignee again
- delegated in: those i need to act on but don't own
- all: self-explanatory - those that I can see: i'm owner, assignee or supervisor

Ensure to unify the code paths relevant for filtering for all the lists.

For protocols the rules are a bit different, consider those filter functions to combine with the todo lists.

- i can see all protocols I own or am an assignee or supervisor for
- i can edit all protocols I own or am a supervisor for

Ideally this would delegate to some framework-level integration using the ACL machinery with roles and permissions.

## Plan-justierungen

delegated_out -> needs to include me NOT being the owner but  supervisor on a delegated team


delegated_in -> not both roles for team member, only direct assignee or assignee team member and not owner



* [x] viewing a protocol run should open by expanding the todo card and displaying the protocol items nested? but might be too busy in the UI, especially on mobile

* [x] when entering a new todo, keep the keyboard focus in the entry field afterwards so i can continue
      adding more items from the keyboard

* [x] the input for new todos in the active and scheduled todo forms break the input-group-text with the shortcut hints on a new line

* [x] the focus highlight ring is partially hidden behind the input-group-text - it doesn't need to go around the input-group-text but should not be covered by it - the input-group-text should not overlay the input area itself but stick to it cleanly

* [x] only show the tag quick choice pills while the composite field is focused

## Lets improve protocol runs (specifically when shown in the pane on the todo list), but plan first:

- [x] move completed items to the end of the list so that uncompleted items are first and I can
keep using the keyboard to add more

- [x] improve visual response: avoid flickering during reload: reload the completed item partial
  individually and move it to the end using proper htmx mechanics that avoid visual flickering,
  the list should move up smoothly, use htmx for that as wellstil

* [x] the lined background shines through the completed run items




- the title in the details pane doesn't need a field label, just let it consume the whole line width

- tags don't respond to editing (s key or clicking), also they show up with 'none' even though attributes
  should just not be visible when they don't have a value

- combine fields in a reasonable way on the same line to make the display more compact

- frequency doesn't show up after adding - is the details pane correctly reloaded after
  a change?

- allow editing the note with ~

- allow editing assignees with @

- allow adding/removing/editing links

- the popovers are anchored to the todo item, but they should be anchored to the field
  in the details pane (which means it's nece4ssary to making the label visible when
  there is no value yet)

  * [x] extend the run pane into a general "details pane" pane and open that up
      when selecting an item

* [x] show all fields in the details pane, allow editing the values there by clicking
     on them or using the associated keyboard shortcut, choose a styling that displays
     them in a compact fashion, leave out fields without value, allow triggering
     editing the fields using the known short cuts

* [x] add 's' as the shortcut for for editing tags

* [x] when multiple items are selected, only show "X selected, <clear selection>"  in the
     details pane

* [x] remove the features that load an entry back into the composite entry for editing, clean up
      the related code from the composite, too

* [x] reuse the popovers for editing the fields, but make sure they appear aligned
      with the field the user is currently editing (either they cursor/bubble position in the composite
      or the field in the details panel)
* [x] ~~initial import vom rtm (incl. archive)?~~



- [x] simplify openeing the edit panel further
  use a form for the todo list aggregating all selected checkboxes instead of creating the value list
  on each checkbox
- [x] get rid of the _buildCompositeTextWith ... this should not be needed any longer

refactor the detail/edit pane into a fully native htmx approach

- [x] don't use 'data' attributes on the todo list
- [x] use one endpoint to load the whole detail pane (with edit form etc)
- [x] when changing a value, submit a form and refetch the pane

- [x] use side-channel to trigger a reload of the todo list and

- [x] deleting a link doesn't update the detail page but reloads the list with the recursive bug of loading the full
   main  page into the todo list

Refinement:

- [x] use the same code for all pickers on the composite and the details pane, don't duplicate
  but refactor

- [x] fold the composites quick picker into the tag popup (they already show up in the picker used for the details)

- [x] the @ picker doesn't autocomplete, reusing the code from the composite here will help, too

- [x] when reloading the list after saving details, the list contains (recursively) the whole page

- [x] don't display any field in the details page that is empty, add an indicator (+) next to the title to add
  fields that are missing (or add them when the corresponding key is pressed)

- [x] ensure all pickers close when pressing escape

- [x] add "l" shortcut for the opening the links picker in the details page

- [x] when adding a link to an item that has a due date, it then suddenly shows up with the ^yyyy-mm-dd marker in its
    title and looses the due field?


* [x] switch shift-p and p meaning: shift-p is postpone one day (or to today when overdue) and p triggers the suggestion palette


* [x] swiping is broken, nothing happens


* [x] pressing 'shift-p' on an overdue item postpones it to tomorrow, that's wrong - it should postpone to today

* [x] styling bug on desktops


- [x] make ownership of a todo item required on the database level. ensure that when adding via the "send to shopping cart" from the weekly planner, the current user
  gets ownership.

* [x] marking an item done doesn't update the counts in the header, extract a separate partial for the sub navigation and
      respond to the 'todo-updated' event via hx-trigger


* [ ] on mobile the card view should take up more space and the grayed out layer behind it is missing, stick to bootstrap, hyperscript and htmx to enable it



## unify the lists for done/hold/scheduled with the active todo list. ignore the protocol management.

i started working on this, so pay attention to the changes in progress that reflect a part of what
I'm describing here

-> i'm a bit puzzled around the various list_ variations. those consist of a main page
   which then calls out to / embeds various detail views

   i think we can adapt this to having a single "list" view that calls out to various
   other views so that the dynamic loading of "which embedded partial list view needs to be
   shown" after an action fits. also, the list updates should be triggered by events and not sent through
   the result of an action

-> so, this would also mean to invert the filters and subnavigation: "my tasks / delegated / ... " should go in the subnavigation and "active, on hold" should
   go into the content (the numbers stay in the subnav and become more stable, they should reflect the "active" count of that category)

-> switch all actions (incl. swipe) to rather use the batch-update endpoint instead of individual action
   endpoints ...



- the "hold" list supports the "activate" action but also all other actions


- [x] "hold" must not available in the hold list
- [x] "activate" must be available in the hold list, via keyboard shortcut and by swiping left
- [x] no default actions must be available in the done list, swiping right does nothing
- [x] "reactivate" must be available in the hold list, also activated by swiping left
- [x] the done list only supports the "return to active" action
- [x] swiping right in the done and on hold list should trigger the "return to active"
- [x] the "hold" list supports the "activate" action but also all other actions


- matti doesn't get assiged his task - that was broken in the db ("eltern @matti" instead if {eltern, matti})
  but editing did resolve it
