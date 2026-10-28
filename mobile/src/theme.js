// NewQ theme palettes.
//
// The `dark` palette is the app's original appearance and stays the default.
// The `light` palette follows the NewQ design system: off-white background,
// white cards, #2563EB primary, #10B981 success. Both palettes share the same
// key names so a single buildStyles(c) implementation serves both themes.

export const THEMES = {
  dark: {
    // Base
    navy: '#0B1220',            // base background
    navySoft: '#101B2D',        // soft panel background
    surface: '#142238',         // card background
    surfaceRaised: '#1A2B43',   // raised card background
    surfaceDeep: '#0E192A',     // deep field background (inputs, options)
    optionIdleBg: '#101C2E',    // idle MCQ option background
    selectedOptionBg: '#123044',
    border: '#263B56',
    headerBorder: '#1B2B40',
    fieldBorder: '#24364E',
    accentBorder: '#24506A',

    // Accents
    cyan: '#38BDF8',
    cyanSoft: '#12374B',
    blue: '#2563EB',
    keywordText: '#BAE6FD',

    // Text
    text: '#F1F5F9',
    textSoft: '#CBD5E1',
    muted: '#8EA2BA',
    footerText: '#526780',
    warning: '#FBBF24',

    // Feedback
    success: '#4ADE80',
    successSoft: '#102F2A',
    successBorder: '#26875A',
    successCardBorder: '#1D5946',
    danger: '#FB7185',
    dangerSoft: '#3A202D',
    dangerBorder: '#A64259',

    // Decorative
    orb: '#15334A',
    progressTrack: '#26374E',

    // Status bar
    statusBarContent: 'light-content',
  },

  light: {
    // Base
    navy: '#F8FAFC',            // base background (design-system off-white)
    navySoft: '#EEF2F7',        // soft panel background
    surface: '#FFFFFF',         // card background (design-system white)
    surfaceRaised: '#F1F5F9',
    surfaceDeep: '#F1F5F9',
    optionIdleBg: '#FFFFFF',
    selectedOptionBg: '#DBEAFE',
    border: '#E2E8F0',
    headerBorder: '#E2E8F0',
    fieldBorder: '#CBD5E1',
    accentBorder: '#BFDBFE',

    // Accents
    cyan: '#2563EB',            // design-system primary
    cyanSoft: '#EFF6FF',
    blue: '#2563EB',
    keywordText: '#1D4ED8',

    // Text
    text: '#1F2937',            // design-system main text
    textSoft: '#334155',
    muted: '#64748B',
    footerText: '#94A3B8',
    warning: '#B45309',

    // Feedback
    success: '#10B981',         // design-system secondary
    successSoft: '#ECFDF5',
    successBorder: '#10B981',
    successCardBorder: '#A7F3D0',
    danger: '#EF4444',
    dangerSoft: '#FEF2F2',
    dangerBorder: '#EF4444',

    // Decorative
    orb: '#DBEAFE',
    progressTrack: '#E2E8F0',

    // Status bar
    statusBarContent: 'dark-content',
  },
};

export const THEME_STORAGE_KEY = 'newq-theme';
