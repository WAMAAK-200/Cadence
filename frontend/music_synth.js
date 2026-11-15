/**
 * Cadence (Smart Diary) Generative Web Audio Synthesizer
 * 
 * Generates an algorithmic weekly music composition directly in the browser:
 * - Key / Scale: Driven by average Mood (Major pentatonic for Happy/Calm, Dorian for Reflective, Minor/Aeolian for Stressed/Down)
 * - Tempo (BPM): Driven by average Sleep duration (>8h -> 85 BPM, 6-8h -> 105 BPM, <5h -> 130 BPM)
 * - Tension / Timbre: Controlled by Stress levels (smooth ambient sine waves for low stress vs dissonant intervals/resonant filter for high stress)
 * - Rhythm & Complexity: Driven by Study / Work hours (sparse pulses for low hours vs intricate polyrhythmic arpeggios for high load)
 */

class MusicCompositionSynth {
    constructor() {
        this.audioCtx = null;
        this.isPlaying = false;
        this.currentStep = 0;
        this.timerId = null;
        this.analyser = null;
        this.animationId = null;
        this.canvas = null;
        this.canvasCtx = null;
        this.onStepCallback = null;
        this.onStopCallback = null;
        this.masterGain = null;
        this.filterNode = null;
    }

    initAudio() {
        if (!this.audioCtx) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            this.audioCtx = new AudioContextClass();

            this.masterGain = this.audioCtx.createGain();
            this.masterGain.gain.value = 0.35;

            this.filterNode = this.audioCtx.createBiquadFilter();
            this.filterNode.type = 'lowpass';
            this.filterNode.frequency.value = 2400;

            this.analyser = this.audioCtx.createAnalyser();
            this.analyser.fftSize = 256;

            this.masterGain.connect(this.filterNode);
            this.filterNode.connect(this.analyser);
            this.analyser.connect(this.audioCtx.destination);
        }
        if (this.audioCtx.state === 'suspended') {
            this.audioCtx.resume();
        }
    }

    /**
     * Compute musical parameters from telemetry entries
     */
    computeMusicParams(entries = []) {
        let totalMood = 0, countMood = 0;
        let totalSleep = 0, countSleep = 0;
        let totalStress = 0, countStress = 0;
        let totalHours = 0;

        const moodMap = { happy: 9, calm: 8, reflective: 5, stressed: 2 };

        entries.forEach(e => {
            let moodVal = null;
            if (typeof e.mood === 'number') moodVal = e.mood;
            else if (typeof e.mood === 'string') {
                const k = e.mood.toLowerCase();
                for (const [mName, mVal] of Object.entries(moodMap)) {
                    if (k.includes(mName)) { moodVal = mVal; break; }
                }
            }
            if (moodVal !== null) { totalMood += moodVal; countMood++; }

            if (typeof e.sleepHours === 'number') { totalSleep += e.sleepHours; countSleep++; }
            if (typeof e.stress === 'number') { totalStress += e.stress; countStress++; }
            if (typeof e.studyHours === 'number') totalHours += e.studyHours;
            if (typeof e.workHours === 'number') totalHours += e.workHours;
        });

        const avgMood = countMood > 0 ? (totalMood / countMood) : 7.0;
        const avgSleep = countSleep > 0 ? (totalSleep / countSleep) : 7.5;
        const avgStress = countStress > 0 ? (totalStress / countStress) : 4.0;

        // 1. Scale & Key from Mood
        let scaleName = 'C Major (Uplifting)';
        let baseFrequencies = [261.63, 293.66, 329.63, 392.00, 440.00, 523.25]; // C, D, E, G, A, C5

        if (avgMood >= 7.0) {
            scaleName = 'G Major Pentatonic (Bright & Joyful)';
            baseFrequencies = [196.00, 220.00, 246.94, 293.66, 329.63, 392.00, 440.00, 493.88]; // G, A, B, D, E, G4, A4, B4
        } else if (avgMood >= 4.5) {
            scaleName = 'D Dorian Modal (Reflective & Calm)';
            baseFrequencies = [146.83, 164.81, 174.61, 196.00, 220.00, 246.94, 261.63, 293.66]; // D, E, F, G, A, B, C, D
        } else {
            scaleName = 'A Minor Harmonic (Tense & Emotional)';
            baseFrequencies = [110.00, 123.47, 130.81, 146.83, 164.81, 174.61, 207.65, 220.00]; // A, B, C, D, E, F, G#, A
        }

        // 2. Tempo BPM from Sleep Duration
        let bpm = 90;
        if (avgSleep >= 8.0) {
            bpm = 80; // Slow, restorative, calm
        } else if (avgSleep >= 6.5) {
            bpm = 100; // Balanced flow
        } else if (avgSleep >= 5.0) {
            bpm = 118; // Elevated pacing
        } else {
            bpm = 132; // Hurried, sleep-deprived agitation
        }

        // 3. Tension level from Stress (1-10)
        let tensionLevel = 'Smooth & Consonant';
        let dissonance = 0.0;
        let filterFreq = 3000;
        if (avgStress >= 7.0) {
            tensionLevel = 'High Tension & Resonance';
            dissonance = 0.6;
            filterFreq = 1200; // tight muffled resonance
        } else if (avgStress >= 4.5) {
            tensionLevel = 'Moderate Tension';
            dissonance = 0.25;
            filterFreq = 2200;
        } else {
            tensionLevel = 'Warm & Ambient';
            dissonance = 0.0;
            filterFreq = 3400;
        }

        // 4. Rhythm complexity from Study/Work Hours
        let rhythmComplexity = 'Gentle Ambient Pulse';
        let noteSubdivision = 4; // quarter notes
        if (totalHours >= 25) {
            rhythmComplexity = 'Intricate Poly-rhythmic Arpeggios';
            noteSubdivision = 16;
        } else if (totalHours >= 10) {
            rhythmComplexity = 'Steady 8th-note Counterpoint';
            noteSubdivision = 8;
        }

        return {
            avgMood: Math.round(avgMood * 10) / 10,
            avgSleep: Math.round(avgSleep * 10) / 10,
            avgStress: Math.round(avgStress * 10) / 10,
            totalHours: Math.round(totalHours * 10) / 10,
            scaleName,
            baseFrequencies,
            bpm,
            tensionLevel,
            dissonance,
            filterFreq,
            rhythmComplexity,
            noteSubdivision
        };
    }

    /**
     * Play a single synthesizer tone for a note or day preview
     */
    playTone(freq, duration = 0.5, type = 'sine', dissonance = 0) {
        this.initAudio();
        const now = this.audioCtx.currentTime;

        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();

        osc.type = type;
        osc.frequency.setValueAtTime(freq, now);

        if (dissonance > 0) {
            // Add slight harmonic detune or sub-oscillator for stress tension
            const osc2 = this.audioCtx.createOscillator();
            const gain2 = this.audioCtx.createGain();
            osc2.type = 'sawtooth';
            osc2.frequency.setValueAtTime(freq * (1 + dissonance * 0.06), now);
            gain2.gain.setValueAtTime(0.08 * dissonance, now);
            gain2.gain.exponentialRampToValueAtTime(0.001, now + duration);
            osc2.connect(gain2);
            gain2.connect(this.masterGain);
            osc2.start(now);
            osc2.stop(now + duration);
        }

        gain.gain.setValueAtTime(0.001, now);
        gain.gain.linearRampToValueAtTime(0.25, now + 0.05);
        gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

        osc.connect(gain);
        gain.connect(this.masterGain);

        osc.start(now);
        osc.stop(now + duration);
    }

    /**
     * Play generative weekly composition
     */
    playWeeklyComposition(entries = [], canvasElement = null, onStep = null, onEnd = null) {
        this.stop();
        this.initAudio();

        const params = this.computeMusicParams(entries);
        this.onStepCallback = onStep;
        this.onStopCallback = onEnd;

        if (canvasElement) {
            this.canvas = canvasElement;
            this.canvasCtx = canvasElement.getContext('2d');
            this.startVisualizer();
        }

        this.filterNode.frequency.setValueAtTime(params.filterFreq, this.audioCtx.currentTime);

        const stepDurationMs = (60 / params.bpm) * (4 / params.noteSubdivision) * 1000;
        const totalSteps = 32; // 2 to 4 full bars
        this.currentStep = 0;
        this.isPlaying = true;

        const notes = params.baseFrequencies;
        const noteCount = notes.length;

        this.timerId = setInterval(() => {
            if (!this.isPlaying) {
                clearInterval(this.timerId);
                return;
            }

            // Pick harmonious or rhythmic pitch based on current step
            const patternIndex = this.currentStep % 8;
            let noteIndex = 0;

            if (patternIndex === 0) noteIndex = 0; // Root note on downbeat
            else if (patternIndex === 2) noteIndex = 2 % noteCount;
            else if (patternIndex === 4) noteIndex = 3 % noteCount;
            else if (patternIndex === 6) noteIndex = 4 % noteCount;
            else noteIndex = Math.floor(Math.sin(this.currentStep * 0.8) * (noteCount / 2) + noteCount / 2) % noteCount;

            const freq = notes[noteIndex];
            const synthType = params.avgStress > 6 ? 'triangle' : 'sine';
            const duration = (stepDurationMs / 1000) * 1.5;

            // Trigger tone
            this.playTone(freq, duration, synthType, params.dissonance);

            // Trigger soft bass pulse on bar beats
            if (this.currentStep % 4 === 0) {
                this.playTone(notes[0] / 2, (stepDurationMs / 1000) * 2, 'sine', 0);
            }

            if (typeof this.onStepCallback === 'function') {
                this.onStepCallback(this.currentStep, totalSteps, params);
            }

            this.currentStep++;
            if (this.currentStep >= totalSteps) {
                this.stop();
            }
        }, stepDurationMs);

        return params;
    }

    startVisualizer() {
        if (!this.canvas || !this.analyser) return;
        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
            if (!this.isPlaying) {
                if (this.canvasCtx) {
                    this.canvasCtx.clearRect(0, 0, this.canvas.width, this.canvas.height);
                }
                return;
            }

            this.animationId = requestAnimationFrame(draw);
            this.analyser.getByteTimeDomainData(dataArray);

            const width = this.canvas.width;
            const height = this.canvas.height;
            const ctx = this.canvasCtx;

            ctx.clearRect(0, 0, width, height);
            ctx.lineWidth = 2.5;
            ctx.strokeStyle = '#2563eb';
            ctx.beginPath();

            const sliceWidth = width * 1.0 / bufferLength;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const v = dataArray[i] / 128.0;
                const y = v * height / 2;

                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);

                x += sliceWidth;
            }

            ctx.lineTo(width, height / 2);
            ctx.stroke();
        };

        draw();
    }

    stop() {
        this.isPlaying = false;
        if (this.timerId) {
            clearInterval(this.timerId);
            this.timerId = null;
        }
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
        if (this.canvasCtx && this.canvas) {
            this.canvasCtx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
        if (typeof this.onStopCallback === 'function') {
            this.onStopCallback();
        }
    }
}

// Global singleton instance
window.SmartDiaryMusicSynth = new MusicCompositionSynth();
