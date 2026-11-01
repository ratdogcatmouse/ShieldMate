// Line icons (24 px grid, currentColor). `className="icon"` sizes them inline with text;
// the tab bar sizes its own.
const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
};

const make = (paths, extra = {}) =>
  function Icon({ className = "icon", style }) {
    return (
      <svg className={className} style={style} {...base} {...extra}>
        {paths}
      </svg>
    );
  };

export const Shield = make(<><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 12l2 2 4-4" /></>);
export const ShieldPlain = make(<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />);
export const Check = make(<path d="M5 12l5 5 9-10" />, { strokeWidth: 3 });
export const Cross = make(<path d="M6 6l12 12M18 6L6 18" />, { strokeWidth: 3 });
export const Phone = make(<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />);
export const Clock = make(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>);
export const Chevron = make(<path d="M9 6l6 6-6 6" />);
export const Back = make(<path d="M15 6l-6 6 6 6" />);
export const Calendar = make(<><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>);
export const Home = make(<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />);
export const Target = make(<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /></>);
export const History = make(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>);
export const Menu = make(<path d="M4 7h16M4 12h16M4 17h16" />);
export const Alert = make(<><path d="M12 3.5l9.5 16.5h-19z" /><path d="M12 10v4" /><path d="M12 17.2v.01" /></>);
export const Bars = make(<path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />);
