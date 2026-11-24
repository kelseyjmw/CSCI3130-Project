export const PASSWORD_HELP = 'Use at least 6 characters, including a digit (0-9) and a special character (e.g., @, #, !).';

// ASCII punctuation, matching Python's string.punctuation. Spaces do not count.
const SPECIAL_CHARACTER = /[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]/;

export function passwordError(password) {
    if (!password) return 'Password is required.';
    if ([...password].length < 6) return 'Password must be at least 6 characters long.';
    if (!/[0-9]/.test(password)) return 'Password must contain at least one digit (0-9).';
    if (!SPECIAL_CHARACTER.test(password)) return 'Password must contain at least one special character (e.g., @, #, !).';
    return '';
}

export function calculateStrength(pass) {
    if (!pass) return { score: 0, label: '', color: '#e5e7eb' };
    let score = 0;
    if ([...pass].length >= 6) score += 1;
    if ([...pass].length >= 10) score += 1;
    if (/[0-9]/.test(pass)) score += 1;
    if (SPECIAL_CHARACTER.test(pass)) score += 1;
    // Good and Strong are reserved for passwords that meet every required rule.
    if (passwordError(pass)) score = Math.min(score, 2);

    switch (score) {
      case 1:
        return { score: 1, label: 'Weak', color: '#ef4444' };
      case 2:
        return { score: 2, label: 'Fair', color: '#f59e0b' };
      case 3:
        return { score: 3, label: 'Good', color: '#3b82f6' };
      case 4:
        return { score: 4, label: 'Strong', color: '#10b981' };
      default:
        return { score: 0, label: 'Too Weak', color: '#ef4444' };
    }
}
