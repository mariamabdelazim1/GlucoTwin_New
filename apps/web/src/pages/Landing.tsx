import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  ChevronRight,
  CircleHelp,
  Layers3,
  ShieldCheck,
  Stethoscope,
  Syringe,
  Utensils,
} from 'lucide-react';
import twinFigure from '../assets/onboarding/digital-twin-no-fade.png';
import './Landing.css';

const features = [
  {
    icon: Activity,
    number: '01',
    title: 'See the whole picture.',
    description: 'Bring glucose readings, meals, and insulin records together.',
  },
  {
    icon: Layers3,
    number: '02',
    title: 'Glucose predictions',
    description: 'GlucoTwin predicts glucose levels for the next 30, 60, and 120 minutes using your digital twin.',
  },
  {
    icon: Syringe,
    number: '03',
    title: 'Bolus & basal optimization',
    description: 'Explore personalized bolus doses and basal rates by simulating different insulin options with your digital twin.',
  },
];

const faqs = [
  ['What is a digital twin?', 'A model-based representation that uses your glucose and treatment history to simulate glucose responses and explore what-if scenarios.'],
  ['What can I track with GlucoTwin?', 'Keep your glucose readings, meal details, and insulin records together so you and your doctor can review your daily history.'],
  ['How do I connect with a doctor?', 'Select a doctor when creating your patient account. You can share your history and exchange messages after the doctor accepts your request.'],
  ['What are what-if scenarios?', 'They let you explore how different meal or insulin inputs may affect simulated glucose, using your digital twin. These are model simulations, not guaranteed outcomes.'],
];

export function Landing() {
  useEffect(() => {
    document.documentElement.classList.add('gt-home-active');
    const page = document.querySelector<HTMLElement>('.gt-home');
    const heroBackground = document.querySelector<HTMLElement>('.gt-hero-background');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const revealTargets = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'));
    let observer: IntersectionObserver | undefined;
    let frame = 0;

    if (!reduceMotion.matches && 'IntersectionObserver' in window) {
      try {
        page?.classList.add('gt-motion-ready');
        observer = new IntersectionObserver((entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            entry.target.classList.add('gt-in-view');
            observer?.unobserve(entry.target);
          }
        }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
        revealTargets.forEach((target) => observer?.observe(target));
      } catch {
        page?.classList.remove('gt-motion-ready');
      }
    }

    const updateWaves = () => {
      frame = 0;
      if (!heroBackground || reduceMotion.matches || window.innerWidth < 821) return;
      const progress = Math.min(window.scrollY, heroBackground.offsetHeight);
      heroBackground.style.setProperty('--gt-wave-shift', `${progress * 0.055}px`);
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(updateWaves);
    };
    const onMotionChange = () => {
      if (reduceMotion.matches) {
        heroBackground?.style.removeProperty('--gt-wave-shift');
        page?.classList.remove('gt-motion-ready');
        revealTargets.forEach((target) => target.classList.add('gt-in-view'));
      } else {
        onScroll();
      }
    };

    updateWaves();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    reduceMotion.addEventListener('change', onMotionChange);

    return () => {
      document.documentElement.classList.remove('gt-home-active');
      observer?.disconnect();
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      reduceMotion.removeEventListener('change', onMotionChange);
      if (frame) window.cancelAnimationFrame(frame);
      heroBackground?.style.removeProperty('--gt-wave-shift');
    };
  }, []);

  return (
    <main className="gt-home">
      <div className="gt-hero-background">
        <header className="gt-nav gt-container">
          <Link className="gt-brand" to="/" aria-label="GlucoTwin home">
            <span className="gt-brand-symbol"><Activity size={25} /></span>
            <span>Gluco<span>Twin</span><small>YOUR HEALTH. IN SYNC.</small></span>
          </Link>
          <nav className="gt-nav-actions" aria-label="Account navigation">
            <Link to="/login" className="gt-sign-in">Sign in <ArrowUpRight size={15} /></Link>
            <Link to="/login/patient?action=register" className="gt-button gt-button-small">Create account <ArrowRight size={15} /></Link>
          </nav>
        </header>

        <section className="gt-hero gt-container" aria-labelledby="gt-home-title">
          <div className="gt-hero-copy">
            <h1 id="gt-home-title" className="gt-product-title">Gluco<span>Twin</span></h1>
            <p className="gt-hero-description">Meet the digital twin that brings your glucose, daily habits, and care team together—so every day feels a little easier to understand.</p>
            <div className="gt-hero-buttons">
              <Link to="/login/patient?action=register" className="gt-button">Create an account <ArrowRight size={18} /></Link>
              <a href="#how-it-works" className="gt-text-link">Explore GlucoTwin <span><ArrowDown size={16} /></span></a>
            </div>
            <div className="gt-hero-footnote"><ShieldCheck size={17} /><span>Built around you. Connected to your doctor.</span></div>
          </div>
          <div className="gt-twin-art">
            <img src={twinFigure} alt="A person wearing a glucose sensor connected to an anatomical digital twin and AI model" />
            <p>A digital twin, built around you.</p>
          </div>
        </section>

        <div className="gt-context-strip gt-container" aria-label="Connected health information">
          <span>YOUR DAY, CONNECTED</span>
          <div><Activity size={18} /> Glucose history</div>
          <div><Utensils size={18} /> Meals &amp; insulin</div>
          <div><Layers3 size={18} /> Digital twin insights</div>
          <div><Stethoscope size={18} /> Your care team</div>
        </div>
      </div>

      <section id="how-it-works" className="gt-how gt-container" aria-labelledby="gt-features-title">
        <div className="gt-section-top" data-reveal>
          <p className="gt-eyebrow">LESS FRAGMENTED. MORE CONNECTED.</p>
          <h2 id="gt-features-title">One place. A fuller picture.</h2>
        </div>
        <div className="gt-feature-grid">
          {features.map(({ icon: Icon, number, title, description }, index) => (
            <article key={number} className={`gt-feature gt-reveal-delay-${index + 1}`} data-reveal>
              <div className="gt-feature-top"><span className="gt-feature-icon"><Icon size={25} /></span><span>{number}</span></div>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="questions" className="gt-faq gt-container" aria-labelledby="gt-faq-title">
        <div className="gt-faq-intro" data-reveal>
          <p className="gt-eyebrow">A LITTLE MORE CLARITY</p>
          <h2 id="gt-faq-title">Good questions.<br />Clear answers.</h2>
          <CircleHelp size={38} aria-hidden="true" />
        </div>
        <div className="gt-faq-list" data-reveal>
          {faqs.map(([question, answer]) => (
            <details key={question}>
              <summary>{question}<ChevronRight size={18} aria-hidden="true" /></summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className="gt-footer gt-container">
        <Link to="/" className="gt-brand" aria-label="GlucoTwin home"><span className="gt-brand-symbol"><Activity size={22} /></span><span>Gluco<span>Twin</span></span></Link>
        <p>A digital twin. A more connected journey.</p>
        <span>© 2026 GlucoTwin</span>
      </footer>
    </main>
  );
}
