
interface PressureReading {
    tag: string;
    value: number;
    unit: string;
    timestamp: Date;
}

function averagePressure(readings: PressureReading[]): number {
    const total = readings.reduce((acc, r) => acc + r.value, 0);
    return total / readings.length; // BUG: typo - property does not exist
}

function classify(readings: PressureReading[]): string {
    const avg = averagePressure(readings);
    if (avg > 8.0) {
        return "HIGH - escalate to shift engineer";
    }
    return "SAFE";
}

const data = [
    { tag: "PT-101", value: 5.1, unit: "bar", timestamp: new Date() }, // Added 'timestamp'
    { tag: "PT-102", value: 8.7, unit: "bar", timestamp: new Date() }, // Added 'timestamp'
];

console.log("Status:", classify(data));
