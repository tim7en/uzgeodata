import React from 'react';
import Term from './Term.jsx';
import { BASIS } from './assessmentModel.js';
import './upstreamInsights.css';

/**
 * The five answers a water manager needs, first in the report. Each carries what
 * it rests on, so a forecast is never read as a measurement and an unanswered
 * question is visibly unanswered.
 */
export default function BasinAssessment({ assessment }) {
  if (!assessment?.length) return null;
  return <section className="assess" aria-label="Basin assessment">
    <h4><Term id="basin_assessment">Basin assessment</Term></h4>
    <p className="assess-lede">Generated from the figures below; each answer says what it rests on.</p>
    <ol>{assessment.map(item => <li key={item.id} className={`assess-${item.basis}`}>
      <h5>{item.question}</h5>
      <p>{item.answer}</p>
      <span className="assess-basis"><Term id={`basis_${item.basis}`}>{BASIS[item.basis]}</Term></span>
    </li>)}</ol>
  </section>;
}
