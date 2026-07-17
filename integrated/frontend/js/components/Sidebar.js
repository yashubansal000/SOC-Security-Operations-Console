// // Sidebar Component: Renders collapsible, animated navigation.
// const anime = window.anime;

// const ICONS = {
//   overview: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9"></rect><rect x="14" y="3" width="7" height="5"></rect><rect x="14" y="12" width="7" height="9"></rect><rect x="3" y="16" width="7" height="5"></rect></svg>`,
//   incidents: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
//   evidence: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`,
//   hypotheses: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1 0-4.12 2.5 2.5 0 0 1 0-4.12A2.5 2.5 0 0 1 7.04 2.13 2.5 2.5 0 0 1 9.5 2z"></path><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 0-4.12 2.5 2.5 0 0 0 0-4.12 2.5 2.5 0 0 0-2.46-8.31 2.5 2.5 0 0 0-2.46-.13z"></path></svg>`,
//   graph: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>`,
//   topology: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="16" y="16" width="6" height="6" rx="1"></rect><rect x="2" y="16" width="6" height="6" rx="1"></rect><rect x="9" y="2" width="6" height="6" rx="1"></rect><path d="M12 8v8"></path><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"></path></svg>`,
//   timeline: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`,
//   shap: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="18" x2="15" y2="18"></line><line x1="3" y1="6" x2="18" y2="6"></line></svg>`,
//   audit: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`
// };

// export class Sidebar {
//   constructor(containerId, activeView, onViewChange) {
//     this.container = document.querySelector(containerId);
//     this.activeView = activeView;
//     this.onViewChange = onViewChange;
//     this.badgeCount = 0;
//     this.menuItems = [
//       { id: 'overview', label: 'Analytics Dashboard' },
//       { id: 'incidents', label: 'Incident Desk', badge: true },
//       { id: 'evidence', label: 'Incident Details' },
//       { id: 'hypotheses', label: 'Hypotheses Engine' },
//       { id: 'shap', label: 'What-if Simulator' },
//       { id: 'graph', label: 'Knowledge Graph' },
//       { id: 'topology', label: 'Network Topology' },
//       { id: 'timeline', label: 'Incident Timeline' },
//       { id: 'audit', label: 'Security SIEM Logs' }
//     ];
//   }

//   render(badgeCount = 0) {
//     if (!this.container) return;
//     this.badgeCount = badgeCount;

//     let html = `<ul class="nav" id="sidebarNav">`;
//     for (const item of this.menuItems) {
//       const activeClass = this.activeView === item.id ? 'active' : '';
//       const badgeHtml = (item.badge && this.badgeCount > 0)
//         ? `<span class="badge-count" id="sidebarBadge">${this.badgeCount}</span>`
//         : '';
      
//       html += `
//         <li data-view="${item.id}" class="${activeClass}">
//           <span class="ico">${ICONS[item.id]}</span>
//           <span class="lbl">${item.label}</span>
//           ${badgeHtml}
//         </li>
//       `;
//     }
//     html += `</ul>`;
    
//     html += `
//       <div class="sidebar-footer">
//         SOC Tier: <b>L2 Analyst</b><br>
//         Console: <b id="sidebarStatus">Online</b>
//       </div>
//     `;

//     this.container.innerHTML = html;
//     this.bindEvents();
//   }

//   bindEvents() {
//     const listItems = this.container.querySelectorAll('#sidebarNav li');
//     listItems.forEach(li => {
//       li.addEventListener('click', () => {
//         const viewId = li.dataset.view;
//         this.setActive(viewId);
//         this.onViewChange(viewId);
//       });
//     });
//   }

//   setActive(viewId) {
//     this.activeView = viewId;
//     const listItems = this.container.querySelectorAll('#sidebarNav li');
//     listItems.forEach(li => {
//       const match = li.dataset.view === viewId;
//       li.classList.toggle('active', match);
      
//       if (match && anime) {
//         // Subtle click pulse animation
//         anime({
//           targets: li,
//           scale: [0.98, 1],
//           duration: 250,
//           easing: 'easeOutQuad'
//         });
//       }
//     });
//   }

//   updateBadge(count) {
//     this.badgeCount = count;
//     const badgeEl = document.getElementById('sidebarBadge');
//     if (badgeEl) {
//       if (count > 0) {
//         badgeEl.textContent = count;
//         badgeEl.style.display = 'inline-block';
//       } else {
//         badgeEl.style.display = 'none';
//       }
//     } else if (count > 0) {
//       // Re-render to add badge
//       this.render(count);
//     }
//   }
// }


// Sidebar Component: Renders collapsible, animated navigation.
const anime = window.anime;

const ICONS = {
  overview: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9"></rect><rect x="14" y="3" width="7" height="5"></rect><rect x="14" y="12" width="7" height="9"></rect><rect x="3" y="16" width="7" height="5"></rect></svg>`,
  incidents: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
  evidence: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`,
  hypotheses: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1 0-4.12 2.5 2.5 0 0 1 0-4.12A2.5 2.5 0 0 1 7.04 2.13 2.5 2.5 0 0 1 9.5 2z"></path><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 0-4.12 2.5 2.5 0 0 0 0-4.12 2.5 2.5 0 0 0-2.46-8.31 2.5 2.5 0 0 0-2.46-.13z"></path></svg>`,
  graph: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>`,
  topology: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="16" y="16" width="6" height="6" rx="1"></rect><rect x="2" y="16" width="6" height="6" rx="1"></rect><rect x="9" y="2" width="6" height="6" rx="1"></rect><path d="M12 8v8"></path><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"></path></svg>`,
  timeline: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`,
  shap: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="18" x2="15" y2="18"></line><line x1="3" y1="6" x2="18" y2="6"></line></svg>`,
//   replay: `
// <svg xmlns="http://www.w3.org/2000/svg"
//      width="18"
//      height="18"
//      viewBox="0 0 24 24"
//      fill="none"
//      stroke="currentColor"
//      stroke-width="2"
//      stroke-linecap="round"
//      stroke-linejoin="round">
//   <polygon points="5 3 19 12 5 21 5 3"></polygon>
// </svg>
// `,
  audit: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`
};

export class Sidebar {
  constructor(containerId, activeView, onViewChange) {
    this.container = document.querySelector(containerId);
    this.activeView = activeView;
    this.onViewChange = onViewChange;
    this.badgeCount = 0;
    this.menuItems = [
      { id: 'overview', label: 'Analytics Dashboard' },
      { id: 'incidents', label: 'Incident Desk', badge: true },
      { id: 'evidence', label: 'Incident Details' },
      { id: 'hypotheses', label: 'Hypotheses Engine' },
      { id: 'shap', label: 'What-if Simulator' },
      { id: 'graph', label: 'Knowledge Graph' },
      { id: 'topology', label: 'Network Topology' },
      { id: 'timeline', label: 'Incident Timeline' },
      // { id: 'replay', label: 'Network Replay' },
      { id: 'audit', label: 'Security SIEM Logs' }
    ];
  }

  render(badgeCount = 0) {
    if (!this.container) return;
    this.badgeCount = badgeCount;

    let html = `<ul class="nav" id="sidebarNav">`;
    for (const item of this.menuItems) {
      const activeClass = this.activeView === item.id ? 'active' : '';
      const badgeHtml = (item.badge && this.badgeCount > 0)
        ? `<span class="badge-count" id="sidebarBadge">${this.badgeCount}</span>`
        : '';
      
      html += `
        <li data-view="${item.id}" class="${activeClass}">
          <span class="ico">${ICONS[item.id]}</span>
          <span class="lbl">${item.label}</span>
          ${badgeHtml}
        </li>
      `;
    }
    html += `</ul>`;
    
    html += `
      <div class="sidebar-footer">
        SOC Tier: <b>L2 Analyst</b><br>
        Console: <b id="sidebarStatus">Online</b>
      </div>
    `;

    this.container.innerHTML = html;
    this.bindEvents();
  }

  bindEvents() {
    const listItems = this.container.querySelectorAll('#sidebarNav li');
    listItems.forEach(li => {
      li.addEventListener('click', () => {
        const viewId = li.dataset.view;
        this.setActive(viewId);
    //     li.addEventListener('click', () => {
    // const viewId = li.dataset.view;

    // if (viewId === "replay") {
    //     window.open("http://localhost:5173", "_blank");
    //     return;
      
    // }

    // this.setActive(viewId);
    this.onViewChange(viewId);
// });
      });
    });
  }

  setActive(viewId) {
    this.activeView = viewId;
    const listItems = this.container.querySelectorAll('#sidebarNav li');
    listItems.forEach(li => {
      const match = li.dataset.view === viewId;
      li.classList.toggle('active', match);
      
      if (match && anime) {
        // Subtle click pulse animation
        anime({
          targets: li,
          scale: [0.98, 1],
          duration: 250,
          easing: 'easeOutQuad'
        });
      }
    });
  }

  updateBadge(count) {
    this.badgeCount = count;
    const badgeEl = document.getElementById('sidebarBadge');
    if (badgeEl) {
      if (count > 0) {
        badgeEl.textContent = count;
        badgeEl.style.display = 'inline-block';
      } else {
        badgeEl.style.display = 'none';
      }
    } else if (count > 0) {
      // Re-render to add badge
      this.render(count);
    }
  }
}