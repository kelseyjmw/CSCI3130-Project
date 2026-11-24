import { calculateStrength, PASSWORD_HELP } from '../utils/passwordStrength';

export default function PasswordStrength({ password }) {
    const strength = calculateStrength(password);
    return (
        <div style={{ marginTop: 8, fontSize: 13 }}>
            <p>{PASSWORD_HELP}</p>
            {password && (
                <>
                    <p>Strength: <strong style={{ color: strength.color }}>{strength.label}</strong></p>
                    <div role="meter" aria-label="Password strength" aria-valuemin={0}
                        aria-valuemax={4} aria-valuenow={strength.score} aria-valuetext={strength.label}
                        style={{ height: 6, backgroundColor: '#e5e7eb', borderRadius: 3 }}>
                        <div style={{ height: '100%', width: `${strength.score * 25}%`,
                            backgroundColor: strength.color, borderRadius: 3 }} />
                    </div>
                </>
            )}
        </div>
    );
}
