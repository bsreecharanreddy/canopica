/**
 * The Canopica rules engine: SNAP eligibility as DMN decision tables, plus a thin
 * evaluation library around them.
 *
 * <p>This package has no Spring, no database, and no clock of its own. It takes
 * facts and already-resolved policy parameters and returns a decision plus a
 * trace, which is what makes every rule table-driven testable and what makes an
 * evaluation reproducible years after it was made.
 */
package canopica.rules;
