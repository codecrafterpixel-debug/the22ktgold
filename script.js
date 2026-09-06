document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Menu Toggle
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const navLinks = document.getElementById('navLinks');

    if (mobileMenuBtn && navLinks) {
        mobileMenuBtn.addEventListener('click', () => {
            navLinks.classList.toggle('active');
            
            // Hamburger animation
            const spans = mobileMenuBtn.querySelectorAll('span');
            if (navLinks.classList.contains('active')) {
                spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
                spans[1].style.opacity = '0';
                spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
            } else {
                spans[0].style.transform = 'none';
                spans[1].style.opacity = '1';
                spans[2].style.transform = 'none';
            }
        });
    }

    // 2. Scroll Animations (Fade Up)
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, observerOptions);

    const fadeElements = document.querySelectorAll('.fade-up');
    fadeElements.forEach(el => observer.observe(el));

    // 3. Hero Slider Logic
    const slides = document.querySelectorAll('.slide');
    const dots = document.querySelectorAll('.slider-dot');
    const prevBtn = document.querySelector('.slider-prev');
    const nextBtn = document.querySelector('.slider-next');
    
    if (slides.length > 0) {
        let currentSlide = 0;
        let slideInterval;

        function goToSlide(n) {
            slides[currentSlide].classList.remove('active');
            if (dots[currentSlide]) dots[currentSlide].classList.remove('active');
            currentSlide = (n + slides.length) % slides.length;
            slides[currentSlide].classList.add('active');
            if (dots[currentSlide]) dots[currentSlide].classList.add('active');
        }

        function nextSlide() {
            goToSlide(currentSlide + 1);
        }

        function prevSlide() {
            goToSlide(currentSlide - 1);
        }

        dots.forEach((dot, index) => {
            dot.addEventListener('click', () => {
                goToSlide(index);
                resetInterval();
            });
        });

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                nextSlide();
                resetInterval();
            });
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                prevSlide();
                resetInterval();
            });
        }

        function resetInterval() {
            clearInterval(slideInterval);
            slideInterval = setInterval(nextSlide, 5000);
        }

        resetInterval();
    }
});

// ════════════════════════════════════════════
// 5. SECURE REAL-TIME GOLD RATE INTEGRATION
// ════════════════════════════════════════════

let currentLiveRates = {
    gold22k: 12110,
    gold24k: 13210,
    gold18k: 9910,
    change22k: 0,
    change24k: 0,
    change18k: 0,
    changePercent: 0,
    formattedTime: ''
};

// Initial load + Auto-refresh every 60 seconds
document.addEventListener('DOMContentLoaded', () => {
    fetchRealGoldRates();
    setInterval(fetchRealGoldRates, 60000); // Auto-refresh every 60s
});

async function fetchRealGoldRates() {
    const syncTimeEl = document.getElementById('board_sync_time');
    const statusBadgeEl = document.getElementById('rate_status_badge');
    if (syncTimeEl) syncTimeEl.textContent = 'Updating live market rates...';

    let data = null;

    // Step 1: Fetch securely from Backend API (/api/gold-rates)
    try {
        const response = await fetch('/api/gold-rates');
        if (response.ok) {
            data = await response.json();
        }
    } catch (apiErr) {
        // Fallback for static/file preview environment
        try {
            const fallbackRes = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=inr&include_24hr_change=true');
            if (fallbackRes.ok) {
                const fbJson = await fallbackRes.json();
                const goldOzInr = fbJson['pax-gold'].inr;
                const changePct = fbJson['pax-gold'].inr_24h_change || 0;
                const r24 = goldOzInr / 31.1034768;
                const r22 = r24 * (22 / 24);
                const r18 = r24 * (18 / 24);
                const ch24 = r24 * (changePct / 100);

                const now = new Date();
                data = {
                    provider: 'Spot Bullion Feed',
                    formattedTime: now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }) + ' IST',
                    gold: {
                        "24k": { perGram: r24, per10g: r24 * 10, change: ch24, changePercent: changePct },
                        "22k": { perGram: r22, per10g: r22 * 10, change: ch24 * (22 / 24), changePercent: changePct },
                        "18k": { perGram: r18, per10g: r18 * 10, change: ch24 * (18 / 24), changePercent: changePct }
                    }
                };
            }
        } catch (e) {
            console.warn('Using baseline cached rates');
        }
    }

    if (data && data.gold) {
        const g24 = data.gold['24k'];
        const g22 = data.gold['22k'];
        const g18 = data.gold['18k'];

        currentLiveRates = {
            gold24k: g24.perGram,
            gold22k: g22.perGram,
            gold18k: g18.perGram,
            change24k: g24.change,
            change22k: g22.change,
            change18k: g18.change,
            changePercent: g24.changePercent,
            formattedTime: data.formattedTime || (new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }) + ' IST')
        };

        updateRateUI(currentLiveRates);

        if (syncTimeEl) {
            syncTimeEl.textContent = `Last updated: ${currentLiveRates.formattedTime}`;
        }
        if (statusBadgeEl) {
            statusBadgeEl.innerHTML = `<span class="live-pulse-dot"></span> LIVE MARKET RATE`;
        }

        calculateGoldPrice();
    }
}

function formatChangeMarkup(amount, percent) {
    const isPositive = amount > 0;
    const isNeutral = amount === 0;
    const arrow = isPositive ? '▲ +' : (isNeutral ? '' : '▼ −');
    const color = isPositive ? '#22C55E' : (isNeutral ? '#A3A3A3' : '#EF4444');
    const absAmount = Math.abs(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const absPercent = Math.abs(percent).toFixed(2);

    return `<span style="color:${color}; font-weight:700; font-size:0.88rem;">${arrow}₹${absAmount} (${isPositive ? '+' : (isNeutral ? '' : '−')}${absPercent}%)</span>`;
}

function updateRateUI(rates) {
    // 1. Ticker Elements
    const t22 = document.getElementById('ticker_22k_val');
    const t22c = document.getElementById('ticker_22k_chg');
    if (t22) t22.textContent = '₹' + rates.gold22k.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '/g';
    if (t22c) t22c.innerHTML = formatChangeMarkup(rates.change22k, rates.changePercent);

    const t24 = document.getElementById('ticker_24k_val');
    const t24c = document.getElementById('ticker_24k_chg');
    if (t24) t24.textContent = '₹' + rates.gold24k.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '/g';
    if (t24c) t24c.innerHTML = formatChangeMarkup(rates.change24k, rates.changePercent);

    const t18 = document.getElementById('ticker_18k_val');
    const t18c = document.getElementById('ticker_18k_chg');
    if (t18) t18.textContent = '₹' + rates.gold18k.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '/g';
    if (t18c) t18c.innerHTML = formatChangeMarkup(rates.change18k, rates.changePercent);

    // 2. Rate Board Elements
    const b22_1 = document.getElementById('board_22k_1g');
    const b22_10 = document.getElementById('board_22k_10g');
    const b22_c = document.getElementById('board_22k_chg');
    if (b22_1) b22_1.textContent = '₹' + rates.gold22k.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (b22_10) b22_10.textContent = '₹' + (rates.gold22k * 10).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (b22_c) b22_c.innerHTML = formatChangeMarkup(rates.change22k, rates.changePercent);

    const b24_1 = document.getElementById('board_24k_1g');
    const b24_10 = document.getElementById('board_24k_10g');
    const b24_c = document.getElementById('board_24k_chg');
    if (b24_1) b24_1.textContent = '₹' + rates.gold24k.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (b24_10) b24_10.textContent = '₹' + (rates.gold24k * 10).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (b24_c) b24_c.innerHTML = formatChangeMarkup(rates.change24k, rates.changePercent);

    const b18_1 = document.getElementById('board_18k_1g');
    const b18_10 = document.getElementById('board_18k_10g');
    const b18_c = document.getElementById('board_18k_chg');
    if (b18_1) b18_1.textContent = '₹' + rates.gold18k.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (b18_10) b18_10.textContent = '₹' + (rates.gold18k * 10).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (b18_c) b18_c.innerHTML = formatChangeMarkup(rates.change18k, rates.changePercent);
}

// 6. Interactive Price Calculator using Real Live Rates
function calculateGoldPrice() {
    const purityEl = document.getElementById('calc_purity');
    const gramsEl = document.getElementById('calc_grams');
    const makingEl = document.getElementById('calc_making');
    const totalDisplay = document.getElementById('calc_total_display');
    const breakdownDisplay = document.getElementById('calc_breakdown_display');

    if (!purityEl || !gramsEl || !makingEl || !totalDisplay) return;

    const purity = purityEl.value;
    const grams = parseFloat(gramsEl.value) || 0;
    const makingPerGram = parseFloat(makingEl.value) || 0;

    let ratePerGram = currentLiveRates.gold22k;
    if (purity === '24') ratePerGram = currentLiveRates.gold24k;
    else if (purity === '18') ratePerGram = currentLiveRates.gold18k;

    const goldCost = Math.round(grams * ratePerGram);
    const makingCost = Math.round(grams * makingPerGram);
    const total = goldCost + makingCost;

    totalDisplay.textContent = '₹' + total.toLocaleString('en-IN');
    if (breakdownDisplay) {
        breakdownDisplay.textContent = `Gold (${grams}g × ₹${ratePerGram.toLocaleString('en-IN', { maximumFractionDigits: 0 })}) + Making (₹${makingCost.toLocaleString('en-IN')})`;
    }
}

function bookGoldRate() {
    const purityEl = document.getElementById('calc_purity');
    const gramsEl = document.getElementById('calc_grams');
    const totalDisplay = document.getElementById('calc_total_display');

    const purity = purityEl ? purityEl.value : '22';
    const grams = gramsEl ? (gramsEl.value || '10') : '10';
    const total = totalDisplay ? totalDisplay.textContent : '₹0';

    let rateUsed = currentLiveRates.gold22k;
    if (purity === '24') rateUsed = currentLiveRates.gold24k;
    else if (purity === '18') rateUsed = currentLiveRates.gold18k;

    const msg = `Hi THE 22KT GOLD, I want to lock/inquire today's Gold Rate based on the live calculator:\n\n*Purity:* ${purity}KT Gold (₹${rateUsed.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/g)\n*Weight:* ${grams} grams\n*Estimated Amount:* ${total}\n*Rate Time:* ${currentLiveRates.formattedTime || 'Today'}\n\nPlease confirm booking and order procedure.`;
    window.open(`https://wa.me/919429616414?text=${encodeURIComponent(msg)}`, '_blank');
}


// ════════════════════════════════════════════
// AUTH MODAL — Login / Signup
// ════════════════════════════════════════════

(function initAuthModal() {
    const overlay = document.getElementById('authModal');
    const closeBtn = document.getElementById('authModalClose');
    if (!overlay) return;

    // Auto-open after 2 seconds (only once per session)
    const alreadyShown = sessionStorage.getItem('authModalShown');
    if (!alreadyShown) {
        setTimeout(() => {
            openAuthModal();
            sessionStorage.setItem('authModalShown', '1');
        }, 2000);
    }

    // Close on overlay click (outside modal box)
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeAuthModal();
    });

    // Close on X button
    if (closeBtn) closeBtn.addEventListener('click', closeAuthModal);

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.classList.contains('active')) closeAuthModal();
    });
})();

function openAuthModal() {
    const overlay = document.getElementById('authModal');
    if (overlay) {
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeAuthModal() {
    const overlay = document.getElementById('authModal');
    if (overlay) {
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }
}

function switchAuthTab(tab) {
    const loginForm  = document.getElementById('loginForm');
    const signupForm = document.getElementById('signupForm');
    const tabLogin   = document.getElementById('tabLogin');
    const tabSignup  = document.getElementById('tabSignup');
    const success    = document.getElementById('authSuccess');

    if (success) success.style.display = 'none';

    if (tab === 'login') {
        if (loginForm)  loginForm.style.display  = 'flex';
        if (signupForm) signupForm.style.display = 'none';
        if (tabLogin)   tabLogin.classList.add('active');
        if (tabSignup)  tabSignup.classList.remove('active');
    } else {
        if (loginForm)  loginForm.style.display  = 'none';
        if (signupForm) signupForm.style.display = 'flex';
        if (tabLogin)   tabLogin.classList.remove('active');
        if (tabSignup)  tabSignup.classList.add('active');
    }
}

function handleLogin(e) {
    e.preventDefault();
    const email    = document.getElementById('loginEmail')?.value?.trim();
    const password = document.getElementById('loginPassword')?.value;
    if (!email || !password) return;

    // Persist login state in localStorage
    localStorage.setItem('22ktUser', JSON.stringify({ email, loggedIn: true }));
    showAuthSuccess();
}

function handleSignup(e) {
    e.preventDefault();
    const first = document.getElementById('signupFirst')?.value?.trim();
    const email = document.getElementById('signupEmail')?.value?.trim();
    if (!first || !email) return;

    localStorage.setItem('22ktUser', JSON.stringify({ name: first, email, loggedIn: true }));
    showAuthSuccess();
}

function showAuthSuccess() {
    const loginForm  = document.getElementById('loginForm');
    const signupForm = document.getElementById('signupForm');
    const success    = document.getElementById('authSuccess');
    const tabs       = document.querySelector('.auth-tabs');
    if (loginForm)  loginForm.style.display  = 'none';
    if (signupForm) signupForm.style.display = 'none';
    if (tabs)       tabs.style.display       = 'none';
    if (success)    success.style.display    = 'block';
}

function togglePwd(inputId, btn) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isText = input.type === 'text';
    input.type = isText ? 'password' : 'text';
    btn.textContent = isText ? '👁' : '🙈';
}

function socialLogin(provider) {
    alert(`${provider} login integration requires OAuth setup. Please contact admin@22ktgold.com`);
}
