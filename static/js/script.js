document.addEventListener('DOMContentLoaded', () => {
    // --- Theme Toggle ---
    const themeToggle = document.getElementById('theme-toggle');
    const htmlEl = document.documentElement;
    const icon = themeToggle.querySelector('i');

    function updateIcon(theme) {
        icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
    }

    // Init
    const savedTheme = localStorage.getItem('theme') || 'light';
    htmlEl.setAttribute('data-theme', savedTheme);
    updateIcon(savedTheme);

    themeToggle.addEventListener('click', () => {
        const current = htmlEl.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        htmlEl.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
        updateIcon(next);
    });
});

// --- Cart Logic ---
let currentPizzaId = null;
let basePrice = 0;

function openCustomizeModal(id, name, price) {
    currentPizzaId = id;
    basePrice = parseFloat(price);
    
    document.getElementById('modalPizzaName').innerText = name;
    document.getElementById('modalBasePrice').innerText = '₹' + basePrice.toFixed(2);
    
    // Reset form
    document.getElementById('sizeSelect').value = 'Medium';
    document.getElementById('crustSelect').value = 'Hand Tossed';
    document.querySelectorAll('.extra-check').forEach(el => el.checked = false);
    
    updatePrice();
    new bootstrap.Modal(document.getElementById('customizeModal')).show();
}

function updatePrice() {
    let total = basePrice;
    const size = document.getElementById('sizeSelect').value;
    const crust = document.getElementById('crustSelect').value;
    
    if (size === 'Large') total += 150;
    if (size === 'Small') total -= 50;
    if (crust === 'Cheese Burst') total += 99;
    
    document.querySelectorAll('.extra-check:checked').forEach(el => {
        total += parseFloat(el.value);
    });
    
    document.getElementById('finalPrice').innerText = total.toFixed(2);
}

// Updated: Add to Cart with Quantity Handling
function addToCartWithCustomization() {
    // ... (Existing gathering of size/crust/extras) ...
    const size = document.getElementById('sizeSelect').value;
    const crust = document.getElementById('crustSelect').value;
    const extras = Array.from(document.querySelectorAll('.extra-check:checked')).map(el => el.dataset.name);
    const total = document.getElementById('finalPrice').innerText;

    const payload = {
        id: currentPizzaId,
        name: document.getElementById('modalPizzaName').innerText,
        price: basePrice,
        size: size,
        crust: crust,
        extras: extras,
        total_price: total
    };

    fetch('/api/add_to_cart', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if(data.status === 'success') {
            bootstrap.Modal.getInstance(document.getElementById('customizeModal')).hide();
            // Show notification or reload page
            location.reload(); 
        } else if (data.redirect) {
            window.location.href = data.redirect;
        }
    });
}

// NEW: Update Quantity in Cart Page
function updateQuantity(index, change) {
    fetch('/update_cart_qty', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({index: index, change: change})
    })
    .then(res => res.json())
    .then(data => {
        if(data.status === 'success') {
            location.reload(); // Reload to reflect price changes
        }
    });
}