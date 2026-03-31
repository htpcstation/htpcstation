.pragma library

// JumpHelper.js — shared quick-jump logic for grid and list views.
//
// LT/RT (Key_Home/Key_End, exposed as keys.isPageUp()/keys.isPageDown()) jump
// to the next/previous letter when sorted alphabetically, or ±10 items otherwise.

/**
 * Returns the uppercase first letter of a name, stripping a leading "The ".
 * Returns "" if the name is empty or falsy.
 */
function firstLetter(name) {
    if (!name) return ""
    var s = name.trim()
    if (s.length > 4 && s.substring(0, 4).toLowerCase() === "the ") s = s.substring(4)
    return s.charAt(0).toUpperCase()
}

/**
 * Scans from currentIndex in direction to find the first item whose uppercase
 * first letter differs from the current item's.
 *
 * @param {number} count        - total item count
 * @param {number} currentIndex - current focused index
 * @param {function} nameGetter - (index: number) => string
 * @param {number} direction    - 1 (forward) or -1 (backward)
 * @returns {number} target index
 */
function findNextLetter(count, currentIndex, nameGetter, direction) {
    if (count === 0 || currentIndex < 0) return currentIndex

    var currentName = nameGetter(currentIndex)
    var currentLetter = firstLetter(currentName)

    var i = currentIndex + direction
    while (i >= 0 && i < count) {
        var name = nameGetter(i)
        var letter = firstLetter(name)
        if (letter !== currentLetter) return i
        i += direction
    }
    // Reached the end — stay at last/first item
    return Math.max(0, Math.min(count - 1, i))
}

/**
 * Returns the target index to jump to.
 *
 * When sortKey is "az" or "za", jumps to the next/previous letter boundary.
 * Otherwise, jumps ±10 items (clamped to [0, count-1]).
 *
 * @param {number} count        - total item count (view.count)
 * @param {number} currentIndex - current focused index
 * @param {string|null} sortKey - current sort key ("az", "za", "recent", "", null, …)
 * @param {function} nameGetter - (index: number) => string
 * @param {number} direction    - 1 (RT/PageDown) or -1 (LT/PageUp)
 * @returns {number} target index
 */
function jumpIndex(count, currentIndex, sortKey, nameGetter, direction) {
    if (count === 0) return currentIndex
    if (sortKey === "az" || sortKey === "za") {
        return findNextLetter(count, currentIndex, nameGetter, direction)
    } else {
        var target = currentIndex + (direction * 10)
        return Math.max(0, Math.min(count - 1, target))
    }
}
