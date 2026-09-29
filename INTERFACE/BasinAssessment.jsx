import React from 'react';
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
    <h4>Basin assessment</h4>
    <p className="assess-lede">Generated from the figures below; each answer says what it rests on.</p>
    <ol>{assessment.map(item => <li key={item.id} className={`assess-${item.basis}`}>
      <h5>{item.question}</h5>
      <p>{item.answer}</p>
      <span className="assess-basis">{BASIS[item.basis]}</span>
    </li>)}</ol>
  </section>;
}
