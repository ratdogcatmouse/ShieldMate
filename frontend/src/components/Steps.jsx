import { Icon } from "../icons.jsx";

// "Do these now": numbered steps. Action IDs never change in translated steps.
// `call` is {name, phone} for the CALL_SAVED_IT step's call button.
export default function Steps({ steps, call, callLabel = "Call" }) {
  if (!steps || steps.length === 0) return null;
  return (
    <div className="steps">
      {steps.map((step, i) => (
        <div className="step" key={`${step.action}-${i}`}>
          {/* STEP_TICKING slot (features.js): becomes a tick button with "done by" once built. Not built. */}
          <div className="step-toggle" style={{ cursor: "default" }}>
            <span className="check">{i + 1}</span>
            <span className="text">{step.text}</span>
          </div>
          {step.action === "CALL_SAVED_IT" && call?.phone && (
            <a className="btn btn-tint call" href={`tel:${call.phone.replace(/\s/g, "")}`}>
              <Icon name="phone" /> {callLabel} {call.name}
            </a>
          )}
        </div>
      ))}
    </div>
  );
}
