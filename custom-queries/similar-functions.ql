/**
 * @name Similar functions (relaxed threshold)
 * @description Find functions that are very similar to each other
 * @kind problem
 * @problem.severity recommendation
 * @precision medium
 * @id py/similar-function-relaxed
 * @tags maintainability
 *       duplicate-code
 */

import python

from Function f1, Function f2
where f1 != f2
  and f1.getLocation().getFile() = f2.getLocation().getFile()
  and f1.getNumLines() > 5
  and f2.getNumLines() > 5
  and f1.getName() != f2.getName()
  and exists(string s1, string s2 |
    s1 = f1.getABodyStmt().toString() and
    s2 = f2.getABodyStmt().toString() and
    s1 = s2
  )
select f1, "This function appears very similar to $@.", f2, f2.getName()
