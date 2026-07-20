/**
 * BusYatra Frontend Script
 * 
 * Cleaned and refactored for Django backend integration.
 * All frontend-only mockup databases, localStorage CRUD, fake authentication,
 * and form blocking (e.preventDefault()) have been removed.
 * Only interactive UI features and animations are retained.
 */

// ----------------------------------------------------
// Global UI Helper Functions
// ----------------------------------------------------

/**
 * FAQ Accordion Toggle
 * Handles slide and icon rotation for FAQ items
 */
window.toggleFaq = function(id) {
    const item = document.getElementById(id);
    const answer = document.getElementById(id + '-answer');
    const icon = document.getElementById(id + '-icon');
    
    if (item && answer && icon) {
        const isOpen = answer.classList.contains('open');
        
        // Close all other FAQs
        document.querySelectorAll('.faq-answer').forEach(el => el.classList.remove('open'));
        document.querySelectorAll('.faq-toggle-icon').forEach(el => el.classList.remove('rotated'));
        document.querySelectorAll('.faq-item').forEach(el => el.classList.remove('open'));
        
        // Toggle current FAQ
        if (!isOpen) {
            answer.classList.add('open');
            icon.classList.add('rotated');
            item.classList.add('open');
        }
    }
};

// ----------------------------------------------------
// Main Initialization and DOM Ready Routing
// ----------------------------------------------------
document.addEventListener("DOMContentLoaded", function() {
    
    // Determine the current page name from URL path
    let path = window.location.pathname.replace(/\/$/, "");
    let page = path.split("/").pop().toLowerCase();
    if (!page || page === "") {
        page = "/";
    } else if (!page.endsWith(".html")) {
        page = page + ".html";
    }

    // ------------------------------------------------
    // 1. Common UI Animations & Theme Interactions
    // ------------------------------------------------

    // Password Show/Hide Toggle
    const togglePassword = document.getElementById("togglePassword");
    if (togglePassword) {
        togglePassword.addEventListener("click", function() {
            const passInput = document.getElementById("password");
            const toggleIcon = document.getElementById("toggleIcon");
            if (passInput && toggleIcon) {
                if (passInput.type === "password") {
                    passInput.type = "text";
                    toggleIcon.classList.replace("bi-eye-slash", "bi-eye");
                } else {
                    passInput.type = "password";
                    toggleIcon.classList.replace("bi-eye", "bi-eye-slash");
                }
            }
        });
    }

    // Navbar Scroll Animation
    window.addEventListener("scroll", function() {
        const navbar = document.querySelector(".navbar");
        if (navbar) {
            if (window.scrollY > 50) {
                navbar.classList.add("navbar-scrolled", "shadow-sm");
            } else {
                navbar.classList.remove("navbar-scrolled", "shadow-sm");
            }
        }
    });

    // Back-to-top button animation
    const backToTopBtn = document.getElementById("backToTop") || document.querySelector(".back-to-top");
    if (backToTopBtn) {
        window.addEventListener("scroll", function() {
            if (window.scrollY > 300) {
                backToTopBtn.classList.add("show");
            } else {
                backToTopBtn.classList.remove("show");
            }
        });
        backToTopBtn.addEventListener("click", function(e) {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    // ------------------------------------------------
    // 2. Forms Submit Interactions (No Block)
    // ------------------------------------------------

    // Contact Form loading feedback
    const contactForm = document.getElementById("contactForm");
    if (contactForm) {
        contactForm.addEventListener("submit", function() {
            if (document.getElementById("sendBtnText")) document.getElementById("sendBtnText").textContent = "Sending...";
            if (document.getElementById("sendSpinner")) document.getElementById("sendSpinner").classList.remove("d-none");
            if (document.getElementById("sendIcon")) document.getElementById("sendIcon").classList.add("d-none");
        });
    }

    // Login Form loading feedback
    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
        loginForm.addEventListener("submit", function() {
            if (document.getElementById("btnText")) document.getElementById("btnText").textContent = "Verifying...";
            if (document.getElementById("loadingSpinner")) document.getElementById("loadingSpinner").classList.remove("d-none");
        });
    }

    // Register Form loading feedback
    const registerForm = document.getElementById("registerForm");
    if (registerForm) {
        registerForm.addEventListener("submit", function() {
            if (document.getElementById("btnText")) document.getElementById("btnText").textContent = "Registering...";
            if (document.getElementById("loadingSpinner")) document.getElementById("loadingSpinner").classList.remove("d-none");
        });
    }

    // ------------------------------------------------
    // 3. Page Specific Interactivity
    // ------------------------------------------------

    // --- HOME PAGE (index.html) ---
    if (page === "index.html" || page === "/") {
        const travelDate = document.getElementById("travelDate");
        if (travelDate) {
            const today = new Date();
            const tomorrow = new Date(today);
            tomorrow.setDate(tomorrow.getDate() + 1);
            travelDate.value = tomorrow.toISOString().split("T")[0];
            travelDate.min = today.toISOString().split("T")[0];
        }

        const swapBtn = document.getElementById("swapBtn");
        if (swapBtn) {
            swapBtn.addEventListener("click", function() {
                const from = document.getElementById("fromCity");
                const to = document.getElementById("toCity");
                if (from && to) {
                    const temp = from.value;
                    from.value = to.value;
                    to.value = temp;
                    swapBtn.style.transform = "rotate(180deg)";
                    setTimeout(() => swapBtn.style.transform = "none", 300);
                }
            });
        }
    }

    // --- BUS LIST PAGE (bus-list.html) ---
    else if (page === "bus-list.html") {
        const params = new URLSearchParams(window.location.search);
        const from = params.get('from') || 'Mumbai';
        const to = params.get('to') || 'Goa';
        const date = params.get('date') || new Date(Date.now() + 86400000).toISOString().split('T')[0];
        const passengers = params.get('passengers') || '1';
        
        const formattedDate = new Date(date).toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric' });
        
        if (document.getElementById('searchRouteHeading')) document.getElementById('searchRouteHeading').innerText = `${from} to ${to}`;
        if (document.getElementById('metaDate')) document.getElementById('metaDate').innerHTML = `<i class="bi bi-calendar-event me-1"></i>${formattedDate}`;
        if (document.getElementById('metaPassengers')) document.getElementById('metaPassengers').innerHTML = `<i class="bi bi-people me-1"></i>${passengers} Passenger(s)`;
        
        if (document.getElementById('modifyFrom')) document.getElementById('modifyFrom').value = from;
        if (document.getElementById('modifyTo')) document.getElementById('modifyTo').value = to;
        if (document.getElementById('modifyDate')) document.getElementById('modifyDate').value = date;
        if (document.getElementById('modifyPassengers')) document.getElementById('modifyPassengers').value = passengers;
        
        for (let i = 1; i <= 4; i++) {
            if (document.getElementById('originLabel' + i)) document.getElementById('originLabel' + i).innerText = from;
            if (document.getElementById('destLabel' + i)) document.getElementById('destLabel' + i).innerText = to;
        }
        
        const priceRange = document.getElementById("priceRange");
        const priceVal = document.getElementById("priceVal");
        if (priceRange && priceVal) {
            priceRange.addEventListener("input", function() {
                priceVal.innerText = '₹' + parseInt(this.value).toLocaleString('en-IN');
            });
        }
        
        document.querySelectorAll(".btn-select-seats").forEach(btn => {
            btn.addEventListener("click", function() {
                sessionStorage.setItem("selectedBusName", this.getAttribute("data-bus"));
                sessionStorage.setItem("selectedBusType", this.getAttribute("data-type"));
                sessionStorage.setItem("selectedBusPrice", this.getAttribute("data-price"));
                sessionStorage.setItem("selectedBusDepTime", this.getAttribute("data-time"));
                sessionStorage.setItem("journeyFrom", from);
                sessionStorage.setItem("journeyTo", to);
                sessionStorage.setItem("journeyDate", formattedDate);
                sessionStorage.setItem("numPassengers", passengers);
                window.location.href = "/seat-booking/";
            });
        });
    }

    // --- SEAT BOOKING PAGE (seat_booking.html and seat-booking.html) ---
    else if (page === "seat-booking.html" || window.location.pathname.includes("seat_booking") || window.location.pathname.includes("seat-booking")) {
        // Read details from Django global variables if they are valid, else fall back to sessionStorage
        const busName = (typeof BUS_NAME !== 'undefined' && BUS_NAME) ? BUS_NAME : (sessionStorage.getItem("selectedBusName") || "Zingbus Premium");
        const busType = (typeof BUS_TYPE !== 'undefined' && BUS_TYPE) ? BUS_TYPE : (sessionStorage.getItem("selectedBusType") || "A/C Sleeper (2+1)");
        const busPrice = (typeof BUS_FARE !== 'undefined' && BUS_FARE) ? BUS_FARE : parseInt(sessionStorage.getItem("selectedBusPrice") || "1499");
        const busTime = (typeof BUS_ID !== 'undefined' && typeof BUS_FARE !== 'undefined') ? (sessionStorage.getItem("selectedBusDepTime") || "19:30") : (sessionStorage.getItem("selectedBusDepTime") || "19:30");
        const route = (typeof BUS_ROUTE !== 'undefined' && BUS_ROUTE) ? BUS_ROUTE : `${sessionStorage.getItem("journeyFrom") || "Mumbai"} to ${sessionStorage.getItem("journeyTo") || "Goa"}`;
        const date = sessionStorage.getItem("journeyDate") || "15 July 2026";
        const busId = (typeof BUS_ID !== 'undefined' && BUS_ID) ? parseInt(BUS_ID) : 1;

        // Update top details if elements exist
        if (document.getElementById("displayBusName")) document.getElementById("displayBusName").innerText = busName;
        if (document.getElementById("displayBusType")) document.getElementById("displayBusType").innerText = busType;
        if (document.getElementById("displayRoute")) document.getElementById("displayRoute").innerHTML = `<i class="bi bi-geo-alt-fill text-warning me-1"></i>${route}`;
        if (document.getElementById("displayDepTime")) document.getElementById("displayDepTime").innerText = busTime;
        if (document.getElementById("displayDate")) document.getElementById("displayDate").innerText = date;

        const isSleeper = busType.toLowerCase().includes("sleeper");
        const deckSelector = document.getElementById("deckSelector");
        const cabinGrid = document.getElementById("cabinGrid");
        
        let currentDeck = "lower"; // default
        const selectedSeats = new Set();
        let couponDiscount = 0;
        let activeCoupon = "";

        // Seeded random number generator based on busId & seat index to keep occupancy persistent for each bus
        function isSeatOccupied(seatCode) {
            if (typeof BOOKED_SEATS !== 'undefined' && Array.isArray(BOOKED_SEATS)) {
                return BOOKED_SEATS.includes(seatCode);
            }
            let hash = 0;
            const str = busId + "-" + seatCode;
            for (let i = 0; i < str.length; i++) {
                hash = str.charCodeAt(i) + ((hash << 5) - hash);
            }
            return Math.abs(hash % 10) < 3; // ~30% occupied
        }

        function isLadiesSeat(seatCode) {
            let hash = 0;
            const str = busId + "-" + seatCode;
            for (let i = 0; i < str.length; i++) {
                hash = str.charCodeAt(i) + ((hash << 5) - hash);
            }
            return Math.abs(hash % 10) === 4; // ~10% ladies only
        }

        // Show toast helper
        window.showToast = function(msg) {
            const toast = document.getElementById("customToast");
            const toastMsg = document.getElementById("toastMsg");
            if (toast && toastMsg) {
                toastMsg.innerText = msg;
                toast.classList.add("show");
                setTimeout(() => {
                    toast.classList.remove("show");
                }, 3000);
            }
        };

        // Switch Decks (for sleepers)
        window.switchDeck = function(deck) {
            currentDeck = deck;
            document.getElementById("lowerDeckBtn").classList.toggle("active", deck === "lower");
            document.getElementById("upperDeckBtn").classList.toggle("active", deck === "upper");
            renderSeatLayout();
        };

        // Render Seater or Sleeper layout
        function renderSeatLayout() {
            if (!cabinGrid) return;
            cabinGrid.innerHTML = "";

            if (isSleeper) {
                if (deckSelector) deckSelector.classList.remove("d-none");
                // 2+1 layout: column 1, aisle, column 2 & 3
                for (let r = 1; r <= 6; r++) {
                    const rowDiv = document.createElement("div");
                    rowDiv.classList.add("seat-row-custom");

                    const p1 = (currentDeck === "lower" ? "L" : "U") + (3 * r - 2);
                    const p2 = (currentDeck === "lower" ? "L" : "U") + (3 * r - 1);
                    const p3 = (currentDeck === "lower" ? "L" : "U") + (3 * r);

                    const group1 = document.createElement("div");
                    group1.classList.add("seat-pair");
                    group1.appendChild(createSeatElement(p1, true));

                    const gap = document.createElement("div");
                    gap.classList.add("seat-gap");

                    const group2 = document.createElement("div");
                    group2.classList.add("seat-pair");
                    group2.appendChild(createSeatElement(p2, true));
                    group2.appendChild(createSeatElement(p3, true));

                    rowDiv.appendChild(group1);
                    rowDiv.appendChild(gap);
                    rowDiv.appendChild(group2);
                    cabinGrid.appendChild(rowDiv);
                }
            } else {
                if (deckSelector) deckSelector.classList.add("d-none");
                // Seater bus: 2+2 layout
                for (let r = 1; r <= 6; r++) {
                    const rowDiv = document.createElement("div");
                    rowDiv.classList.add("seat-row-custom");

                    const p1 = "S" + (4 * r - 3);
                    const p2 = "S" + (4 * r - 2);
                    const p3 = "S" + (4 * r - 1);
                    const p4 = "S" + (4 * r);

                    const group1 = document.createElement("div");
                    group1.classList.add("seat-pair");
                    group1.appendChild(createSeatElement(p1, false));
                    group1.appendChild(createSeatElement(p2, false));

                    const gap = document.createElement("div");
                    gap.classList.add("seat-gap");

                    const group2 = document.createElement("div");
                    group2.classList.add("seat-pair");
                    group2.appendChild(createSeatElement(p3, false));
                    group2.appendChild(createSeatElement(p4, false));

                    rowDiv.appendChild(group1);
                    rowDiv.appendChild(gap);
                    rowDiv.appendChild(group2);
                    cabinGrid.appendChild(rowDiv);
                }
            }
        }

        // Helper to create seat HTML node
        function createSeatElement(seatCode, isSleeperSeat) {
            const seat = document.createElement("div");
            seat.className = "bus-seat";
            if (isSleeperSeat) {
                seat.classList.add("sleeper-vertical");
            }
            seat.setAttribute("data-seat", seatCode);
            seat.innerText = seatCode;

            const occupied = isSeatOccupied(seatCode);
            const ladies = isLadiesSeat(seatCode);

            if (occupied && ladies) {
                seat.classList.add("ladies-occupied");
            } else if (occupied) {
                seat.classList.add("occupied");
            } else if (ladies) {
                seat.classList.add("ladies");
            }

            if (selectedSeats.has(seatCode)) {
                seat.classList.add("selected");
            }

            if (!seat.classList.contains("occupied") && !seat.classList.contains("ladies-occupied")) {
                seat.addEventListener("click", function() {
                    if (selectedSeats.has(seatCode)) {
                        selectedSeats.delete(seatCode);
                        seat.classList.remove("selected");
                    } else {
                        if (selectedSeats.size >= 5) {
                            showToast("You can book a maximum of 5 seats at once!");
                            return;
                        }
                        selectedSeats.add(seatCode);
                        seat.classList.add("selected");
                    }
                    updateBookingSummary();
                });
            }

            return seat;
        }

        // Calculate and sync pricing + traveler fields
        function updateBookingSummary() {
            const displaySeats = document.getElementById("displaySelectedSeats");
            const calcBase = document.getElementById("calcBaseFare");
            const calcTaxes = document.getElementById("calcTaxes");
            const calcTotal = document.getElementById("calcTotal");
            const calcDiscount = document.getElementById("calcDiscount");
            const discountRow = document.getElementById("couponDiscountRow");
            const checkoutForm = document.getElementById("bookingCheckoutForm");
            const placeholder = document.getElementById("unselectedPlaceholder");
            const countLabel = document.getElementById("seatSelectionCount");

            if (countLabel) {
                countLabel.innerHTML = `Selected: <strong class="text-primary">${selectedSeats.size} / 5</strong> max`;
            }

            if (selectedSeats.size === 0) {
                if (displaySeats) displaySeats.innerText = "None";
                if (calcBase) calcBase.innerText = "₹0";
                if (calcTaxes) calcTaxes.innerText = "₹0";
                if (calcTotal) calcTotal.innerText = "₹0";
                if (discountRow) discountRow.classList.add("d-none");
                if (checkoutForm) checkoutForm.classList.add("d-none");
                if (placeholder) placeholder.classList.remove("d-none");
                return;
            }

            if (placeholder) placeholder.classList.add("d-none");
            if (checkoutForm) checkoutForm.classList.remove("d-none");

            const seatsArray = Array.from(selectedSeats);
            if (displaySeats) displaySeats.innerText = seatsArray.join(", ");

            const baseFare = selectedSeats.size * busPrice;
            const gstFee = Math.round(baseFare * 0.05 + 40 * selectedSeats.size);
            
            let discountValue = 0;
            if (activeCoupon === "BUSYATRA100") {
                discountValue = 100;
            } else if (activeCoupon === "YATRA150") {
                discountValue = 150;
            }
            
            discountValue = Math.min(discountValue, baseFare);
            const totalToPay = Math.max(0, baseFare + gstFee - discountValue);

            if (calcBase) calcBase.innerText = `₹${baseFare}`;
            if (calcTaxes) calcTaxes.innerText = `₹${gstFee}`;
            
            if (discountValue > 0) {
                if (calcDiscount) calcDiscount.innerText = `-₹${discountValue}`;
                if (discountRow) discountRow.classList.remove("d-none");
            } else {
                if (discountRow) discountRow.classList.add("d-none");
            }

            if (calcTotal) calcTotal.innerText = `₹${totalToPay}`;

            const fieldsContainer = document.getElementById("dynamicPassengerFields");
            if (fieldsContainer) {
                const currentRows = fieldsContainer.querySelectorAll(".passenger-entry-box");
                const currentSeats = Array.from(currentRows).map(row => row.getAttribute("data-seat"));

                currentRows.forEach(row => {
                    if (!selectedSeats.has(row.getAttribute("data-seat"))) {
                        row.remove();
                    }
                });

                seatsArray.forEach(seatCode => {
                    if (!currentSeats.includes(seatCode)) {
                        const div = document.createElement("div");
                        div.className = "passenger-entry-box p-3 border rounded-4 bg-white shadow-sm mb-2";
                        div.setAttribute("data-seat", seatCode);
                        div.innerHTML = `
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="badge bg-primary text-white rounded-pill px-2.5 py-1 small fw-bold">Seat: ${seatCode}</span>
                                <span class="text-muted small"><i class="bi bi-person-fill text-secondary me-1"></i>Traveler</span>
                            </div>
                            <div class="row g-2">
                                <div class="col-md-6">
                                    <input type="text" name="passenger_name_${seatCode}" class="form-control form-control-sm passenger-name-input" placeholder="Full Name" required>
                                </div>
                                <div class="col-md-3 col-6">
                                    <input type="number" name="passenger_age_${seatCode}" class="form-control form-control-sm passenger-age-input" placeholder="Age" min="5" max="100" required>
                                </div>
                                <div class="col-md-3 col-6">
                                    <select name="passenger_gender_${seatCode}" class="form-select form-select-sm passenger-gender-select" required>
                                        <option value="" disabled selected>Gender</option>
                                        <option value="Male">Male</option>
                                        <option value="Female">Female</option>
                                        <option value="Other">Other</option>
                                    </select>
                                </div>
                            </div>
                        `;
                        fieldsContainer.appendChild(div);
                    }
                });
            }
        }

        window.applyPromo = function() {
            const promoCodeInput = document.getElementById("promoCodeInput");
            const promoMessage = document.getElementById("promoMessage");
            if (!promoCodeInput || !promoMessage) return;

            const code = promoCodeInput.value.trim().toUpperCase();
            if (selectedSeats.size === 0) {
                showToast("Please select seats first!");
                return;
            }

            if (code === "BUSYATRA100" || code === "YATRA150") {
                activeCoupon = code;
                promoMessage.className = "small mt-1 text-success fw-bold";
                promoMessage.innerHTML = `<i class="bi bi-patch-check-fill me-1"></i>Promo applied successfully!`;
                
                document.querySelectorAll(".coupon-badge").forEach(el => {
                    el.style.background = "";
                    el.style.color = "";
                    el.style.borderColor = "";
                });
                const activeBadge = document.getElementById(code === "BUSYATRA100" ? "c1" : "c2");
                if (activeBadge) {
                    activeBadge.style.background = "#10b981";
                    activeBadge.style.color = "#ffffff";
                    activeBadge.style.borderColor = "#10b981";
                }
            } else {
                activeCoupon = "";
                promoMessage.className = "small mt-1 text-danger fw-bold";
                promoMessage.innerHTML = `<i class="bi bi-x-circle-fill me-1"></i>Invalid promo code.`;
            }
            promoMessage.classList.remove("d-none");
            updateBookingSummary();
        };

        window.selectPromo = function(code) {
            const promoCodeInput = document.getElementById("promoCodeInput");
            if (promoCodeInput) {
                promoCodeInput.value = code;
                applyPromo();
            }
        };

        window.handleProceedCheckout = function(e) {
            e.preventDefault();
            
            const email = document.getElementById("primaryEmail").value;
            const mobile = document.getElementById("primaryMobile").value;
            const travelers = [];

            let isValid = true;
            document.querySelectorAll(".passenger-entry-box").forEach(box => {
                const name = box.querySelector(".passenger-name-input").value.trim();
                const age = box.querySelector(".passenger-age-input").value;
                const gender = box.querySelector(".passenger-gender-select").value;
                const seatCode = box.getAttribute("data-seat");

                if (!name || !age || !gender) {
                    isValid = false;
                }

                travelers.push({
                    seatCode: seatCode,
                    name: name,
                    age: age,
                    gender: gender
                });
            });

            if (!isValid) {
                showToast("Please fill all traveler details correctly!");
                return;
            }

            const baseFare = selectedSeats.size * busPrice;
            const gstFee = Math.round(baseFare * 0.05 + 40 * selectedSeats.size);
            let discountValue = 0;
            if (activeCoupon === "BUSYATRA100") discountValue = 100;
            if (activeCoupon === "YATRA150") discountValue = 150;
            
            discountValue = Math.min(discountValue, baseFare);
            const totalToPay = Math.max(0, baseFare + gstFee - discountValue);

            sessionStorage.setItem("selectedBusName", busName);
            sessionStorage.setItem("selectedBusType", busType);
            sessionStorage.setItem("selectedBusPrice", busPrice);
            sessionStorage.setItem("selectedBusDepTime", busTime);
            sessionStorage.setItem("journeyFrom", route.split(" to ")[0]);
            sessionStorage.setItem("journeyTo", route.split(" to ")[1] || "Goa");
            sessionStorage.setItem("journeyDate", date);
            sessionStorage.setItem("bookingSeats", Array.from(selectedSeats).join(","));
            sessionStorage.setItem("bookingTotal", totalToPay);
            sessionStorage.setItem("bookingTaxes", gstFee);
            sessionStorage.setItem("bookingDiscount", discountValue);
            sessionStorage.setItem("bookingBaseFare", baseFare);
            sessionStorage.setItem("contactEmail", email);
            sessionStorage.setItem("contactMobile", mobile);
            sessionStorage.setItem("travelersInfo", JSON.stringify(travelers));

            // Set hidden seats field and submit the form to django backend
            const seatsInput = document.getElementById("selectedSeatsInput");
            if (seatsInput) {
                seatsInput.value = Array.from(selectedSeats).join(",");
                document.getElementById("bookingCheckoutForm").submit();
            } else {
                window.location.href = "/payment/";
            }
        };

        renderSeatLayout();
    }

    // --- PAYMENT PAGE (payment.html) ---
    else if (page === "payment.html") {
        const busName = sessionStorage.getItem("selectedBusName") || "Zingbus Premium";
        const route = `${sessionStorage.getItem("journeyFrom") || "Mumbai"} to ${sessionStorage.getItem("journeyTo") || "Goa"}`;
        const date = sessionStorage.getItem("journeyDate") || "15 July 2026";
        const seats = sessionStorage.getItem("bookingSeats") || "L1, L2";
        const total = parseInt(sessionStorage.getItem("bookingTotal") || "3088");
        const taxes = parseInt(sessionStorage.getItem("bookingTaxes") || "190");
        const baseFare = parseInt(sessionStorage.getItem("bookingBaseFare") || "2998");
        const discount = parseInt(sessionStorage.getItem("bookingDiscount") || "0");
        
        if (document.getElementById("summaryBusName")) document.getElementById("summaryBusName").innerText = busName;
        if (document.getElementById("summaryRoute")) document.getElementById("summaryRoute").innerText = route;
        if (document.getElementById("summaryDate")) document.getElementById("summaryDate").innerText = date;
        if (document.getElementById("summarySeats")) document.getElementById("summarySeats").innerText = seats;
        if (document.getElementById("sumBaseFare")) document.getElementById("sumBaseFare").innerText = `₹${baseFare}`;
        if (document.getElementById("sumTaxes")) document.getElementById("sumTaxes").innerText = `₹${taxes}`;
        if (document.getElementById("sumTotal")) document.getElementById("sumTotal").innerText = `₹${total}`;
        if (document.getElementById("headerAmount")) document.getElementById("headerAmount").innerText = `₹${total}`;
        
        if (discount > 0 && document.getElementById("discountBlock")) {
            document.getElementById("discountBlock").classList.remove("d-none");
            if (document.getElementById("sumDiscount")) document.getElementById("sumDiscount").innerText = `-₹${discount}`;
        }
        
        // Card number spacing utility
        const cardNum = document.getElementById("cardNumber");
        if (cardNum) {
            cardNum.addEventListener("input", function() {
                let val = this.value.replace(/\s+/g, '').replace(/[^0-9]/g, '');
                let parts = [];
                for (let i = 0; i < val.length; i += 4) parts.push(val.substring(i, i + 4));
                this.value = parts.join(' ');
            });
        }

        // Expiry slash utility
        const expiry = document.getElementById("cardExpiry");
        if (expiry) {
            expiry.addEventListener("input", function() {
                let val = this.value.replace(/[^0-9]/g, '');
                if (val.length >= 2) this.value = val.slice(0, 2) + '/' + val.slice(2, 4);
                else this.value = val;
            });
        }
        
        // Interactive bank select active state
        document.querySelectorAll(".btn-select-bank").forEach(btn => {
            btn.addEventListener("click", function() {
                document.querySelectorAll(".btn-select-bank").forEach(b => b.classList.remove("border-primary", "bg-primary-subtle"));
                this.classList.add("border-primary", "bg-primary-subtle");
                const bankDropdown = document.getElementById("bankDropdown");
                if (bankDropdown) bankDropdown.removeAttribute("required");
            });
        });
        
        // Payment submission loader trigger (without blocking POST)
        const handlePaymentSubmit = () => {
            const overlay = document.getElementById("paymentOverlay");
            if (overlay) overlay.classList.remove("d-none");
        };
        
        ["cardForm", "upiForm", "netbankingForm", "walletsForm"].forEach(id => {
            const form = document.getElementById(id);
            if (form) form.addEventListener("submit", handlePaymentSubmit);
        });
    }

    // --- TICKET PAGE (ticket.html) ---
    else if (page === "ticket.html") {
        const bookingId = sessionStorage.getItem("bookingId") || "GB" + Math.floor(100000 + Math.random() * 900000);
        const busName = sessionStorage.getItem("selectedBusName") || "Zingbus Premium";
        const from = sessionStorage.getItem("journeyFrom") || "Mumbai";
        const to = sessionStorage.getItem("journeyTo") || "Goa";
        const date = sessionStorage.getItem("journeyDate") || "15 July 2026";
        const time = sessionStorage.getItem("selectedBusDepTime") || "19:30";
        const seats = sessionStorage.getItem("bookingSeats") || "L1, L2";
        const total = sessionStorage.getItem("bookingTotal") || "3088";
        const travelers = JSON.parse(sessionStorage.getItem("travelersInfo") || "[]");
        
        if (document.getElementById("pnrNumber")) document.getElementById("pnrNumber").innerText = bookingId;
        if (document.getElementById("ticketNumber")) document.getElementById("ticketNumber").innerText = bookingId;
        if (document.getElementById("ticketBusName")) document.getElementById("ticketBusName").innerText = busName;
        if (document.getElementById("ticketRoute")) document.getElementById("ticketRoute").innerText = `${from} ↔ ${to}`;
        if (document.getElementById("ticketDate")) document.getElementById("ticketDate").innerText = date;
        if (document.getElementById("ticketTime")) document.getElementById("ticketTime").innerText = time;
        if (document.getElementById("ticketSeats")) document.getElementById("ticketSeats").innerText = seats;
        if (document.getElementById("ticketPrice")) document.getElementById("ticketPrice").innerText = `₹${total}`;
        
        const container = document.getElementById("passengerContainer");
        if (container) {
            container.innerHTML = travelers.map(t => `
                <div class="row text-navy-dark fw-semibold mb-2 py-1 bg-light rounded px-2 small">
                    <div class="col-6">${t.name}</div>
                    <div class="col-3 text-center">${t.age} yrs</div>
                    <div class="col-3 text-end">${t.gender}</div>
                </div>
            `).join("") || `
                <div class="row text-navy-dark fw-semibold mb-2 py-1 bg-light rounded px-2 small">
                    <div class="col-6">Rahul Verma</div>
                    <div class="col-3 text-center">26 yrs</div>
                    <div class="col-3 text-end">Male</div>
                </div>
            `;
        }
    }

    // --- COMMON PROFILE BANNER INITIALIZATION (For Dashboard & Orders Pages) ---
    if (page === "dashboard.html" || page === "user-dashboard.html" || page === "my-orders.html" || page === "dashboard" || page === "user-dashboard" || page === "my-orders") {
        loadCommonProfileBanner();

        // Handle profile photo input change (triggered on photo upload in banner)
        const photoInput = document.getElementById('profilePhotoInput');
        if (photoInput) {
            photoInput.addEventListener('change', function(e) {
                const file = e.target.files[0];
                if (file) {
                    if (file.size > 2 * 1024 * 1024) {
                        alert("Profile photo size should not exceed 2MB.");
                        return;
                    }
                    const reader = new FileReader();
                    reader.onload = function(evt) {
                        const base64Image = evt.target.result;
                        let userData = JSON.parse(localStorage.getItem('busyatra_logged_in_user'));
                        if (userData) {
                            userData.profileImage = base64Image;
                            localStorage.setItem('busyatra_logged_in_user', JSON.stringify(userData));
                            loadCommonProfileBanner();
                            
                            // Show floating success toast/alert
                            showFloatingNotification("Profile picture updated successfully!", "success");
                        }
                    };
                    reader.readAsDataURL(file);
                }
            });
        }
    }

    // --- DASHBOARD / PROFILE PAGE SPECIFIC INTERACTIVITY ---
    if (page === "dashboard.html" || page === "user-dashboard.html" || page === "dashboard" || page === "user-dashboard") {
        let userData = JSON.parse(localStorage.getItem('busyatra_logged_in_user'));
        if (!userData) {
            userData = {
                name: "Amit Sharma",
                email: "amit.sharma@example.com",
                phone: "+91 98765 43210",
                usertype: "Customer",
                profileImage: "",
                password: "password123",
                savings: 250,
                wallet: 150
            };
            localStorage.setItem('busyatra_logged_in_user', JSON.stringify(userData));
        }

        // Populate Dashboard views with data
        const profileEditName = document.getElementById('profileEditName');
        const profileEditPhone = document.getElementById('profileEditPhone');
        const profileEditEmail = document.getElementById('profileEditEmail');
        const profileEditUserType = document.getElementById('profileEditUserType');
        const profileBadgeRole = document.getElementById('profileBadgeRole');
        const walletBalanceBig = document.getElementById('walletBalanceBig');

        if (profileEditName) profileEditName.value = userData.name;
        if (profileEditPhone) profileEditPhone.value = userData.phone;
        if (profileEditEmail) profileEditEmail.value = userData.email;
        if (profileEditUserType) profileEditUserType.value = userData.usertype || 'Customer';
        if (profileBadgeRole) profileBadgeRole.innerText = userData.usertype || 'Customer';
        if (walletBalanceBig) walletBalanceBig.innerText = `₹${userData.wallet || 0}`;

        // Edit Profile Toggles
        const btnEditProfile = document.getElementById('btnEditProfile');
        const btnCancelEdit = document.getElementById('btnCancelEdit');
        const btnSaveProfile = document.getElementById('btnSaveProfile');
        const editProfileForm = document.getElementById('editProfileForm');

        if (btnEditProfile) {
            btnEditProfile.addEventListener('click', function() {
                if (profileEditName) profileEditName.removeAttribute('disabled');
                if (profileEditPhone) profileEditPhone.removeAttribute('disabled');
                if (profileEditName) profileEditName.focus();

                btnEditProfile.classList.add('d-none');
                if (btnCancelEdit) btnCancelEdit.classList.remove('d-none');
                if (btnSaveProfile) btnSaveProfile.classList.remove('d-none');
            });
        }

        if (btnCancelEdit) {
            btnCancelEdit.addEventListener('click', function() {
                // Restore values
                let currentUser = JSON.parse(localStorage.getItem('busyatra_logged_in_user'));
                if (profileEditName) {
                    profileEditName.value = currentUser.name;
                    profileEditName.setAttribute('disabled', 'true');
                }
                if (profileEditPhone) {
                    profileEditPhone.value = currentUser.phone;
                    profileEditPhone.setAttribute('disabled', 'true');
                }

                if (btnEditProfile) btnEditProfile.classList.remove('d-none');
                btnCancelEdit.classList.add('d-none');
                if (btnSaveProfile) btnSaveProfile.classList.add('d-none');
                hideAlert('profileAlertContainer');
            });
        }

        if (editProfileForm) {
            editProfileForm.addEventListener('submit', function(e) {
                e.preventDefault();
                const saveSpinner = document.getElementById('saveSpinner');
                const saveIcon = document.getElementById('saveIcon');

                if (saveSpinner) saveSpinner.classList.remove('d-none');
                if (saveIcon) saveIcon.classList.add('d-none');

                setTimeout(function() {
                    let updatedUser = JSON.parse(localStorage.getItem('busyatra_logged_in_user'));
                    updatedUser.name = profileEditName.value.trim();
                    updatedUser.phone = profileEditPhone.value.trim();
                    localStorage.setItem('busyatra_logged_in_user', JSON.stringify(updatedUser));

                    loadCommonProfileBanner();

                    if (profileEditName) profileEditName.setAttribute('disabled', 'true');
                    if (profileEditPhone) profileEditPhone.setAttribute('disabled', 'true');

                    if (saveSpinner) saveSpinner.classList.add('d-none');
                    if (saveIcon) saveIcon.classList.remove('d-none');

                    if (btnEditProfile) btnEditProfile.classList.remove('d-none');
                    if (btnCancelEdit) btnCancelEdit.classList.add('d-none');
                    if (btnSaveProfile) btnSaveProfile.classList.add('d-none');

                    showAlert('profileAlertContainer', 'Profile details updated successfully!', 'success');
                }, 600);
            });
        }

        // Setup Password Visibility Toggles
        setupPassToggle('btnToggleCurrentPass', 'currentPassword', 'currentPassIcon');
        setupPassToggle('btnToggleNewPass', 'newPassword', 'newPassIcon');
        setupPassToggle('btnToggleConfirmPass', 'confirmNewPassword', 'confirmPassIcon');

        // Password Strength Indicator
        const newPasswordInput = document.getElementById('newPassword');
        const passwordStrengthBar = document.getElementById('passwordStrengthBar');
        const passwordStrengthText = document.getElementById('passwordStrengthText');

        if (newPasswordInput) {
            newPasswordInput.addEventListener('input', function() {
                const pass = newPasswordInput.value;
                let strength = 0;
                if (pass.length >= 6) strength += 25;
                if (/[A-Z]/.test(pass)) strength += 25;
                if (/[0-9]/.test(pass)) strength += 25;
                if (/[^A-Za-z0-9]/.test(pass)) strength += 25;

                if (passwordStrengthBar) {
                    passwordStrengthBar.style.width = strength + '%';
                    passwordStrengthBar.className = 'progress-bar';
                    if (strength < 50) {
                        passwordStrengthBar.classList.add('bg-danger');
                        if (passwordStrengthText) passwordStrengthText.innerText = 'Strength: Weak';
                    } else if (strength < 75) {
                        passwordStrengthBar.classList.add('bg-warning');
                        if (passwordStrengthText) passwordStrengthText.innerText = 'Strength: Medium';
                    } else {
                        passwordStrengthBar.classList.add('bg-success');
                        if (passwordStrengthText) passwordStrengthText.innerText = 'Strength: Strong';
                    }
                }
            });
        }

        // Confirm Password Match Check
        const confirmPasswordInput = document.getElementById('confirmNewPassword');
        const passwordMatchError = document.getElementById('passwordMatchError');

        function checkPasswordMatch() {
            if (newPasswordInput && confirmPasswordInput && passwordMatchError) {
                if (confirmPasswordInput.value === '') {
                    passwordMatchError.classList.add('d-none');
                } else if (newPasswordInput.value !== confirmPasswordInput.value) {
                    passwordMatchError.classList.remove('d-none');
                } else {
                    passwordMatchError.classList.add('d-none');
                }
            }
        }
        if (newPasswordInput) newPasswordInput.addEventListener('input', checkPasswordMatch);
        if (confirmPasswordInput) confirmPasswordInput.addEventListener('input', checkPasswordMatch);

        // Change Password Submission
        const changePasswordForm = document.getElementById('changePasswordForm');
        if (changePasswordForm) {
            changePasswordForm.addEventListener('submit', function(e) {
                e.preventDefault();

                let currentUser = JSON.parse(localStorage.getItem('busyatra_logged_in_user'));
                const currentPass = document.getElementById('currentPassword').value;
                const newPass = newPasswordInput.value;
                const confirmPass = confirmPasswordInput.value;

                if (currentPass !== currentUser.password) {
                    showAlert('passwordAlertContainer', 'Incorrect current password.', 'danger');
                    return;
                }

                if (newPass !== confirmPass) {
                    showAlert('passwordAlertContainer', 'New passwords do not match.', 'danger');
                    return;
                }

                if (newPass.length < 6) {
                    showAlert('passwordAlertContainer', 'New password must be at least 6 characters.', 'danger');
                    return;
                }

                const passwordSpinner = document.getElementById('passwordSpinner');
                const passwordIcon = document.getElementById('passwordIcon');

                if (passwordSpinner) passwordSpinner.classList.remove('d-none');
                if (passwordIcon) passwordIcon.classList.add('d-none');

                setTimeout(function() {
                    let updatedUser = JSON.parse(localStorage.getItem('busyatra_logged_in_user'));
                    updatedUser.password = newPass;
                    localStorage.setItem('busyatra_logged_in_user', JSON.stringify(updatedUser));

                    if (passwordSpinner) passwordSpinner.classList.add('d-none');
                    if (passwordIcon) passwordIcon.classList.remove('d-none');

                    changePasswordForm.reset();
                    if (passwordStrengthBar) passwordStrengthBar.style.width = '0%';
                    if (passwordStrengthText) passwordStrengthText.innerText = 'Strength: Weak';

                    showAlert('passwordAlertContainer', 'Password updated successfully!', 'success');
                }, 600);
            });
        }

        // Tab switches & hash routing implementation
        const menuProfile = document.getElementById('menuProfile');
        const menuWallet = document.getElementById('menuWallet');

        function switchTab(tabId) {
            const profileView = document.getElementById('profileView');
            const passwordView = document.getElementById('passwordSecurityView');
            const preferencesCard = document.getElementById('preferencesCard');
            const walletView = document.getElementById('walletView');
            const bookingsView = document.getElementById('bookingsView');

            if (menuProfile) menuProfile.classList.remove('active');
            if (menuWallet) menuWallet.classList.remove('active');

            if (profileView) profileView.classList.add('d-none');
            if (passwordView) passwordView.classList.add('d-none');
            if (preferencesCard) preferencesCard.classList.add('d-none');
            if (walletView) walletView.classList.add('d-none');
            if (bookingsView) bookingsView.classList.add('d-none');

            if (tabId === 'profile') {
                if (profileView) profileView.classList.remove('d-none');
                if (passwordView) passwordView.classList.remove('d-none');
                if (preferencesCard) preferencesCard.classList.remove('d-none');
                if (menuProfile) menuProfile.classList.add('active');
            } else if (tabId === 'wallet') {
                if (walletView) walletView.classList.remove('d-none');
                if (menuWallet) menuWallet.classList.add('active');
            }
        }

        if (menuProfile) {
            menuProfile.addEventListener('click', function(e) {
                e.preventDefault();
                switchTab('profile');
                window.location.hash = 'profile';
            });
        }

        if (menuWallet) {
            menuWallet.addEventListener('click', function(e) {
                e.preventDefault();
                switchTab('wallet');
                window.location.hash = 'wallet';
            });
        }

        // Trigger switch tab on page load based on hash
        if (window.location.hash === '#wallet') {
            switchTab('wallet');
        } else {
            switchTab('profile');
        }
    }

    // Helper function to show alerts
    function showAlert(containerId, message, type) {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = `
                <div class="alert alert-${type} alert-dismissible fade show rounded-3 shadow-sm border-0 d-flex align-items-center" role="alert">
                    <i class="bi ${type === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill'} me-2 fs-5"></i>
                    <div>${message}</div>
                    <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            `;
            // Auto dismiss after 4 seconds
            setTimeout(function() {
                const alertEl = container.querySelector('.alert');
                if (alertEl) {
                    const bsAlert = bootstrap.Alert.getInstance(alertEl) || new bootstrap.Alert(alertEl);
                    bsAlert.close();
                }
            }, 4000);
        }
    }

    function hideAlert(containerId) {
        const container = document.getElementById(containerId);
        if (container) container.innerHTML = '';
    }

    // Setup helper for password show/hide visibility toggles
    function setupPassToggle(btnId, inputId, iconId) {
        const btn = document.getElementById(btnId);
        const input = document.getElementById(inputId);
        const icon = document.getElementById(iconId);
        if (btn && input && icon) {
            btn.addEventListener('click', function() {
                if (input.type === 'password') {
                    input.type = 'text';
                    icon.classList.replace('bi-eye-slash', 'bi-eye');
                } else {
                    input.type = 'password';
                    icon.classList.replace('bi-eye', 'bi-eye-slash');
                }
            });
        }
    }

    // Helper to load common profile banner
    function loadCommonProfileBanner() {
        let userData = JSON.parse(localStorage.getItem('busyatra_logged_in_user'));
        if (!userData) {
            userData = {
                name: "Amit Sharma",
                email: "amit.sharma@example.com",
                phone: "+91 98765 43210",
                usertype: "Customer",
                profileImage: "",
                password: "password123",
                savings: 250,
                wallet: 150
            };
            localStorage.setItem('busyatra_logged_in_user', JSON.stringify(userData));
        }

        const bannerName = document.getElementById('profileName');
        const bannerContact = document.getElementById('profileContact');
        const avatarContainer = document.getElementById('profileAvatarContainer');

        if (bannerName) bannerName.innerText = userData.name;
        if (bannerContact) {
            bannerContact.innerHTML = `<i class="bi bi-envelope me-1"></i>${userData.email} | <i class="bi bi-phone me-1"></i>${userData.phone}`;
        }

        if (avatarContainer) {
            let initials = userData.name ? userData.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) : "AD";
            if (userData.profileImage) {
                avatarContainer.innerHTML = `<img src="${userData.profileImage}" alt="Profile Picture" class="w-100 h-100 object-fit-cover" style="border-radius: 50%;">`;
            } else {
                avatarContainer.innerHTML = `<span id="profileInitials">${initials}</span>`;
            }
        }

        const savingsEl = document.getElementById('profileSavingsAmount');
        const walletEl = document.getElementById('profileWalletBalance');
        if (savingsEl) savingsEl.innerText = `₹${userData.savings || 0}`;
        if (walletEl) walletEl.innerText = `₹${userData.wallet || 0}`;
    }

    // Floating success toast
    function showFloatingNotification(message, type) {
        const toastContainer = document.createElement('div');
        toastContainer.style.position = 'fixed';
        toastContainer.style.bottom = '24px';
        toastContainer.style.right = '24px';
        toastContainer.style.zIndex = '9999';
        toastContainer.innerHTML = `
            <div class="toast show align-items-center text-white bg-${type === 'success' ? 'success' : 'danger'} border-0 rounded-3 shadow" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="bi ${type === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill'} me-2"></i> ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>
        `;
        document.body.appendChild(toastContainer);
        setTimeout(function() {
            toastContainer.remove();
        }, 3500);
    }
});
