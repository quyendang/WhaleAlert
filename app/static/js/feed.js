/**
 * Whale Alert — Real-time feed via Server-Sent Events
 */

const CHAIN_COLORS = {
    ETH: 'bg-blue-600', BTC: 'bg-orange-500', BSC: 'bg-yellow-500',
    SOL: 'bg-purple-500', TRX: 'bg-red-500', MATIC: 'bg-violet-500',
};

const EXPLORER_URLS = {
    ETH: 'https://etherscan.io/tx/',
    BTC: 'https://blockstream.info/tx/',
    BSC: 'https://bscscan.com/tx/',
    SOL: 'https://solscan.io/tx/',
    TRX: 'https://tronscan.org/#/transaction/',
    MATIC: 'https://polygonscan.com/tx/',
};

const TYPE_LABELS = {
    exchange_deposit: ['Deposit', 'text-red-400'],
    exchange_withdrawal: ['Withdrawal', 'text-green-400'],
    mint: ['Mint', 'text-yellow-400'],
    burn: ['Burn', 'text-orange-400'],
    transfer: ['Transfer', 'text-gray-400'],
};

let newItemCount = 0;
let eventSource = null;

// ─── Formatting helpers ───────────────────────────────────────────────────────

function formatNative(amount) {
    const n = parseFloat(amount);
    if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
    return n.toLocaleString('en-US', { maximumFractionDigits: 4 });
}

function formatUsd(amount) {
    if (!amount) return '—';
    const n = parseFloat(amount);
    if (n >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
    if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return '$' + (n / 1e3).toFixed(0) + 'K';
    return '$' + n.toFixed(0);
}

function formatAddr(address, label) {
    if (label && label !== 'Unknown') return label;
    if (!address) return '—';
    return address.slice(0, 8) + '...' + address.slice(-4);
}

function formatTime(isoString) {
    const d = new Date(isoString);
    const hms = d.toTimeString().slice(0, 8);
    const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    return `<span class="text-gray-300">${hms}</span><br><span class="text-gray-500">${date}</span>`;
}

// ─── Row builder ─────────────────────────────────────────────────────────────

function buildRow(tx) {
    const chainColor = CHAIN_COLORS[tx.chain] || 'bg-gray-600';
    const [typeLabel, typeColor] = TYPE_LABELS[tx.tx_type] || ['Transfer', 'text-gray-400'];
    const fromIsKnown = tx.from_label && tx.from_label !== 'Unknown';
    const toIsKnown = tx.to_label && tx.to_label !== 'Unknown';
    const explorerUrl = (EXPLORER_URLS[tx.chain] || '#') + tx.tx_hash;

    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-800/50 transition-colors cursor-pointer new-tx-flash';
    row.onclick = () => window.location = `/tx/${tx.id}`;

    row.innerHTML = `
        <td class="px-4 py-3 text-xs">${formatTime(tx.block_time)}</td>
        <td class="px-4 py-3">
            <span class="inline-block ${chainColor} text-white text-xs font-bold px-2 py-0.5 rounded">${tx.chain}</span>
        </td>
        <td class="px-4 py-3 text-right">
            <div class="font-semibold text-white">${formatNative(tx.amount_native)} ${tx.native_symbol}</div>
            <div class="text-gray-400 text-xs">${formatUsd(tx.amount_usd)}</div>
        </td>
        <td class="px-4 py-3 hidden sm:table-cell">
            <span class="${fromIsKnown ? 'text-blue-400 font-medium' : 'text-gray-500 font-mono text-xs'}">
                ${formatAddr(tx.from_address, tx.from_label)}
            </span>
        </td>
        <td class="px-4 py-3 hidden sm:table-cell">
            <span class="${toIsKnown ? 'text-blue-400 font-medium' : 'text-gray-500 font-mono text-xs'}">
                ${formatAddr(tx.to_address, tx.to_label)}
            </span>
        </td>
        <td class="px-4 py-3 hidden md:table-cell">
            <span class="text-xs ${typeColor}">${typeLabel}</span>
        </td>
        <td class="px-4 py-3 text-center hidden lg:table-cell">
            <a href="${explorerUrl}" target="_blank" onclick="event.stopPropagation()"
               class="text-gray-500 hover:text-blue-400 text-xs font-mono transition-colors">
               ${tx.tx_hash.slice(0, 8)}…
            </a>
        </td>
    `;
    return row;
}

// ─── Live feed ────────────────────────────────────────────────────────────────

function connectFeed() {
    if (eventSource) eventSource.close();

    eventSource = new EventSource('/api/v1/transactions/feed');

    eventSource.onopen = () => {
        document.getElementById('connection-banner').classList.add('hidden');
        document.getElementById('live-badge').classList.remove('hidden');
    };

    eventSource.onmessage = (event) => {
        try {
            const tx = JSON.parse(event.data);
            if (tx.error) return;

            // Check active chain filter
            const chainFilter = document.getElementById('filter-chain')?.value;
            if (chainFilter && tx.chain !== chainFilter) return;

            // Check min USD filter
            const minUsd = parseFloat(document.getElementById('filter-min-usd')?.value || 0);
            if (minUsd && parseFloat(tx.amount_usd || 0) < minUsd) return;

            const tbody = document.getElementById('tx-table-body');
            if (!tbody) return;

            // Remove empty state row if present
            const emptyRow = tbody.querySelector('td[colspan]');
            if (emptyRow) emptyRow.parentElement.remove();

            const row = buildRow(tx);

            const isScrolledDown = window.scrollY > 200;
            if (isScrolledDown) {
                newItemCount++;
                const banner = document.getElementById('new-items-banner');
                document.getElementById('new-count').textContent = newItemCount;
                banner.classList.remove('hidden');
            }

            tbody.insertBefore(row, tbody.firstChild);

            // Trim table to 200 rows max
            while (tbody.children.length > 200) {
                tbody.removeChild(tbody.lastChild);
            }
        } catch (e) {
            console.error('Feed parse error:', e);
        }
    };

    eventSource.onerror = () => {
        document.getElementById('connection-banner').classList.remove('hidden');
        document.getElementById('live-badge').classList.add('hidden');
        eventSource.close();
        // Reconnect after 5 seconds
        setTimeout(connectFeed, 5000);
    };
}

// ─── Stats ────────────────────────────────────────────────────────────────────

async function loadStats() {
    try {
        const resp = await fetch('/api/v1/stats/summary');
        if (!resp.ok) return;
        const data = await resp.json();

        document.getElementById('stat-count').textContent =
            (data.total_transactions_24h || 0).toLocaleString();
        document.getElementById('stat-volume').textContent =
            formatUsd(data.total_usd_24h);
        document.getElementById('stat-largest').textContent =
            data.largest_24h ? formatUsd(data.largest_24h.amount_usd) : '—';
        document.getElementById('stat-chains').textContent =
            Object.keys(data.by_chain || {}).length;
    } catch (e) {
        console.warn('Stats load error:', e);
    }
}

// ─── Filters ─────────────────────────────────────────────────────────────────

function applyFilters() {
    const chain = document.getElementById('filter-chain').value;
    const minUsd = document.getElementById('filter-min-usd').value;
    const sort = document.getElementById('filter-sort').value;

    const params = new URLSearchParams();
    if (chain) params.set('chain', chain);
    if (minUsd) params.set('min_usd', minUsd);
    if (sort) params.set('sort', sort);
    params.set('page', '1');

    window.location.href = '/?' + params.toString();
}

function clearFilters() {
    window.location.href = '/';
}

function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    newItemCount = 0;
    document.getElementById('new-items-banner').classList.add('hidden');
}

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    connectFeed();
    // Refresh stats every 60s
    setInterval(loadStats, 60_000);
});
