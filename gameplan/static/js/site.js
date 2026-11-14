/** 
 * Main JavaScript file for the site.
 * This file contains the main JavaScript code for the site, including functionality for the mobile menu, image carousels, and other interactive elements.
 */
document.addEventListener("DOMContentLoaded", () => {
  const menuButton = document.querySelector("[data-menu-toggle]");
  const primaryNav = document.querySelector("[data-primary-nav]");
/* Close the mobile menu when clicking outside of it */
  const closeMobileMenu = () => {
    // Check if the menu button and primary navigation are available. If either is not found, we cannot close the menu, so we return early.
    if (!menuButton || !primaryNav) return;
    menuButton.setAttribute("aria-expanded", "false");   // Set the aria-expanded attribute to false to indicate that the menu is closed.
    primaryNav.classList.remove("open");                 // Remove the "open" class from the primary navigation to hide it.
    document.body.classList.remove("menu-open");        // Re-enable background scrolling by removing the "menu-open" class from the body.
  };
/** 
 * Toggle the mobile menu when the menu button is clicked.
 */
  menuButton?.addEventListener("click", () => {
    // Determine the target state of the menu by checking the current value of the aria-expanded attribute. If it's not "true", we want to open the menu; otherwise, we want to close it.
    const open = menuButton.getAttribute("aria-expanded") !== "true";
    // Sync screen reader state with the menu state by updating the aria-expanded attribute to reflect whether the menu is open or closed.
    menuButton.setAttribute("aria-expanded", String(open));
    primaryNav?.classList.toggle("open", open);
    document.body.classList.toggle("menu-open", open);
  });
  // Close the mobile menu when a link inside the primary navigation is clicked.
  primaryNav
    ?.querySelectorAll("a")
    .forEach((link) => link.addEventListener("click", closeMobileMenu));
  // Reset the mobile menu state when the window is resized to a width greater than 900 pixels. This ensures that the menu is closed when switching from mobile to desktop view.
  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) closeMobileMenu();
  });

  // Dismiss any open account menus when clicking outside of them. This is done by listening for click events on the document and checking if the click target is outside of any open account menus.
  document.addEventListener("click", (event) => {
    document.querySelectorAll("[data-account-menu][open]").forEach((menu) => {
      // keep the menu open if the click target is inside the menu; otherwise, close it by removing the "open" attribute.
      if (!menu.contains(event.target)) menu.removeAttribute("open");
    });
  });

  // Dismiss open mobile and account menus when the Escape key is pressed. This is done by listening for keydown events on the document and checking if the pressed key is "Escape".
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeMobileMenu();
    //Collapse all expanded account dropdowns by removing the "open" attribute from any account menu that is currently open.
    document
      .querySelectorAll("[data-account-menu][open]")
      .forEach((menu) => menu.removeAttribute("open"));
  });
// Set up each image slideshow carousel on the page. Each carousel is identified by the data attribute "data-hero-carousel". The code initializes the carousel functionality, including autoplay, navigation buttons, and dot indicators for each slide.
  document.querySelectorAll("[data-hero-carousel]").forEach((carousel) => {
    // Gather all the slides and dots within the carousel. The slides are identified by the data attribute "data-hero-slide", and the dots are identified by the data attribute "data-hero-dot". If there are fewer than 2 slides, we return early since a carousel is not needed.
    const slides = [...carousel.querySelectorAll("[data-hero-slide]")];
    const dots = [...carousel.querySelectorAll("[data-hero-dot]")];
    //stop here if there are fewer than 2 slides, as a carousel is not needed in that case.
    if (slides.length < 2) return;

    //Check if the user has requested reduced motion in their system preferences. If so, we will not enable autoplay for the carousel.
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    //Track the current slide index, the autoplay timer, whether the user is hovering over the carousel, and the starting position of a pointer event (for swipe gestures).
    let current = 0;               // Which slide is currently being displayed (0-based index).
    let timer = null;              // Holds the countdown timer for autoplaying the slides. If null, autoplay is not active.
    let hovering = false;          // Whether a mouse pointer is currently hovering over the carousel. If true, autoplay will be paused.
    let pointerStart = null;       // Where a finger or mouse pointer started a swipe gesture. Used to determine the direction and distance of the swipe.

    /** This function stops the autoplay of the carousel. */
    const stopAutoplay = () => {
      if (timer) window.clearInterval(timer);
      timer = null;
    };
/** The function that starts the autoplay of the carousel. */
    const startAutoplay = () => {
      stopAutoplay();
      if (reducedMotion || hovering || document.hidden) return;
      timer = window.setInterval(() => show(current + 1, false), 5500); // Change slide every 5.5 seconds
    };
// Switch to a chosen slide and update what visitors see. The restart parameter determines whether to restart the autoplay timer after switching slides.
    const show = (index, restart = true) => {
      // Loop back to the start or end of the slides if the index is out of bounds. The modulo operator ensures that the index wraps around correctly.
      current = (index + slides.length) % slides.length;

      // Go through every slide to show only the current one and hide the others. The "active" class is toggled based on whether the slide index matches the current index, and the "aria-hidden" attribute is updated for accessibility.
      slides.forEach((slide, slideIndex) => {
        const active = slideIndex === current;
        slide.classList.toggle("active", active);              // Show or hide the slide based on whether it's the current one.
        slide.setAttribute("aria-hidden", String(!active));    // Hide inactive slides from screen readers for accessibility.
      });

      // Update the bottom navigation dots to reflect the current slide. The "active" class is toggled for each dot based on whether its index matches the current slide index, and the "aria-current" attribute is updated for accessibility.
      dots.forEach((dot, dotIndex) => {
        const active = dotIndex === current;
        dot.classList.toggle("active", active);                   // Visually highlight the dot corresponding to the current slide.
        dot.setAttribute("aria-current", String(active));         // Tell screen readers which dot is currently active for accessibility.
      });
      // Restart the autoplay timer if the restart parameter is true. This ensures that the carousel continues to automatically switch slides after a manual navigation action.
      if (restart) startAutoplay();
    };

    // Connect the previous and next buttons to the carousel functionality. When clicked, they will show the previous or next slide, respectively.
    carousel
      .querySelector("[data-hero-previous]")
      ?.addEventListener("click", () => show(current - 1));
    carousel
      .querySelector("[data-hero-next]")
      ?.addEventListener("click", () => show(current + 1));

    // Allow visitors to click on the bottom navigation dots to jump directly to a specific slide. Each dot has a data attribute indicating which slide it corresponds to, and clicking it will show that slide.
    dots.forEach((dot) =>
      dot.addEventListener("click", () => show(Number(dot.dataset.heroDot))),
    );
    // Pause automatic slide switching when the user hovers over the carousel, and resume it when they move the mouse away. This improves usability by allowing users to interact with the carousel without it changing slides unexpectedly.
    carousel.addEventListener("mouseenter", () => {
      hovering = true;
      stopAutoplay();
    });
    // Resume automatic slide switching when the user moves the mouse away from the carousel. This allows the carousel to continue autoplaying after the user has finished interacting with it.
    carousel.addEventListener("mouseleave", () => {
      hovering = false;
      startAutoplay();
    });
    // Allow visitors to navigate the carousel using the left and right arrow keys on their keyboard. This improves accessibility by providing an alternative way to switch slides for users who may not be able to use a mouse or touch input.
    carousel.addEventListener("keydown", (event) => {
      // Ignore key presses if the focus is on an input, select, or button element to prevent interfering with form interactions.
      if (/^(INPUT|SELECT|BUTTON)$/.test(event.target.tagName)) return;
      if (event.key === "ArrowLeft") {
        event.preventDefault(); // Stop the browser from scrolling the page when the arrow keys are pressed.
        show(current - 1);
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        show(current + 1);
      }
    });
    
    // Touchsscreens: record where a finger starts, and if it moves far enough left or right, switch slides. This allows users on touch devices to swipe through the carousel.
    carousel.addEventListener(
      "pointerdown",
      (event) => {
        if (event.pointerType === "mouse") return;
        pointerStart = { x: event.clientX, y: event.clientY };
      },
      { passive: true },
    );
    // When the finger is lifted, check how far it moved. If it moved far enough left or right, switch slides accordingly. This provides a natural swipe gesture for navigating the carousel on touch devices.
    carousel.addEventListener(
      "pointerup",
      (event) => {
        if (!pointerStart) return;
        const dx = event.clientX - pointerStart.x;
        const dy = event.clientY - pointerStart.y;
        pointerStart = null;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.2) // Only consider horizontal swipes that are significantly larger than vertical movement.
          show(current + (dx < 0 ? 1 : -1));                        // If the swipe was to the left (dx < 0), go to the next slide; if it was to the right, go to the previous slide.
      },
      { passive: true },
    );
    // Reset the swipe tracking if the pointer is canceled (e.g., if the user lifts their finger outside the carousel). This prevents accidental slide changes when the swipe gesture is interrupted.
    carousel.addEventListener("pointercancel", () => {
      pointerStart = null;
    });

    // Pause the slideshow when the page is hidden (e.g., when the user switches to another tab) and resume it when the page becomes visible again. This conserves resources and ensures that users don't miss slides while they're not looking at the page.
    document.addEventListener("visibilitychange", () =>
      document.hidden ? stopAutoplay() : startAutoplay(),
    );
    // Start the autoplay when the page is first loaded. This begins the automatic slide switching for the carousel.
    startAutoplay();
  });
// Pre-fill the search bar's date picker with today's date and set the minimum selectable date to today. This ensures that users cannot select a past date for their search, improving the user experience and preventing invalid searches.
  const dateInput = document.querySelector('.hero-search input[type="date"]');
  if (dateInput && !dateInput.value) {
    // Adjust for the visitor's local timezone to ensure that the date is accurate regardless of where they are located. This is done by subtracting the timezone offset from the current date and time, converting it to an ISO string, and then extracting just the date portion (YYYY-MM-DD).
    const today = new Date();
    const localToday = new Date(
      today.getTime() - today.getTimezoneOffset() * 60000,
    )
      .toISOString()
      .slice(0, 10);
    dateInput.min = localToday;  // Prevent users from selecting a date earlier than today by setting the minimum date attribute of the date input field.
    dateInput.value = localToday; // set today as the default value of the date input field, so that users see today's date pre-filled when they first load the page.
  }

  //let visitors save their favorite courses by clicking the heart icon. When clicked, the heart icon toggles between a filled and an empty state, indicating whether the course is saved or not. The aria-pressed attribute is also updated for accessibility, allowing screen readers to announce the current state of the button.
  document.querySelectorAll(".heart").forEach((button) => {
    button.addEventListener("click", () => {
      const saved = button.classList.toggle("saved");
      button.innerHTML = saved ? "&#9829;" : "&#9825;"; // Switch between a filled heart (♥) and an empty heart (♡) based on whether the course is saved or not.
      button.setAttribute("aria-pressed", String(saved)); // Tell screen readers whether the button is currently pressed (saved) or not, improving accessibility for users who rely on assistive technologies.
    });
  });
// Let visitors expand and collapse course descriptions by clicking the "Read More" button. When clicked, the button toggles the visibility of the course description and updates its text to "Read Less" or "Read More" accordingly. The aria-expanded attribute is also updated for accessibility, allowing screen readers to announce whether the content is expanded or collapsed.
  document.querySelectorAll(".btn-read-more").forEach((button) => {
    // Find the description text associated with the "Read More" button. The button is expected to be inside a container with the class "course-body", and the description text should have the class "course-desc". If the description text is not found, we return early to avoid errors.
    const text = button.closest(".course-body")?.querySelector(".course-desc");
    if (!text) return;
    button.addEventListener("click", () => {
      const expanded = text.classList.toggle("expanded");           // Show or hide the course description by toggling the "expanded" class on the description text. The expanded variable indicates whether the description is currently expanded or not.
      button.textContent = expanded ? "Read Less" : "Read More";    // Swap the button text between "Read Less" and "Read More" based on whether the description is expanded or collapsed.
      button.setAttribute("aria-expanded", String(expanded));       // Tell screen readers whether the content is currently expanded or collapsed by updating the aria-expanded attribute on the button, improving accessibility for users who rely on assistive technologies.
    });
  });

  // Stop unfinished placeholder links and forms from navigating or submitting. This prevents users from accidentally navigating to a non-existent page or submitting a form that is not yet functional, improving the user experience and preventing errors.
  document.querySelectorAll('a[href="#"]').forEach((link) => {
    link.addEventListener("click", (event) => event.preventDefault());
  });
  // Prevent demo or placeholder forms from submitting. This is useful for forms that are not yet functional or are meant to be used as examples, ensuring that users do not accidentally submit incomplete or non-functional forms.
  document
    .querySelectorAll('form[data-template-placeholder="true"]')
    .forEach((form) => {
      form.addEventListener("submit", (event) => event.preventDefault());
    });
});
/** Sets up the booking popup window once the web page finishes loading. */
document.addEventListener("DOMContentLoaded", () => {
  // Find the booking dialog element on the page. If it doesn't exist, we return early since there's no booking functionality to set up.
  const dialog = document.getElementById("booking-dialog");
  if (!dialog) return;
  // Grab the text spots inside the popup where we will fill in the course name and time when a visitor clicks on a tee time card. These elements are identified by their respective IDs.
  const courseName = document.getElementById("booking-course-name");
  const timeLabel = document.getElementById("booking-time-label");
  const detailsTime = document.getElementById("booking-details-time");

  /** Fills the booking popup with the course name and time from the selected tee time card. */
  const openBooking = (card) => {
    // Read the course name and time from the selected tee time card. The course name is found in an h2 element inside a container with the class "course-info", and the time is found in a time element. We trim any extra whitespace from the text content to ensure clean display in the popup.
    const course = card.querySelector(".course-info h2").textContent.trim();
    const time = card.querySelector("time").textContent.trim();
    // Copy the course name and time into the booking popup's text spots. This updates the popup with the relevant information for the selected tee time card, allowing visitors to see which course and time they are booking.
    courseName.textContent = course;
    timeLabel.textContent = time;
    detailsTime.textContent = time;
    dialog.showModal(); // Open the booking popup as a modal dialog, preventing interaction with the rest of the page until the popup is closed.
  };
/**Connects all tee time card buttons and sets up ways to close the booking popup.
 * 
 * When a user clicks a buttonn on any tee time card, grab that specific card's course name and time, fill the booking popup with that information, and then display the popup. Also, set up event listeners to close the popup when the user clicks a close button or clicks outside the popup.
 */
  document.querySelectorAll(".tee-card button").forEach((button) => {
    button.addEventListener("click", () =>
      openBooking(button.closest(".tee-card")),
    );
  });
  // Close the booking popup when the user clicks any button with the data attribute "data-close-booking". This allows users to easily dismiss the popup by clicking a designated close button.
  dialog.querySelectorAll("[data-close-booking]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
  // Also close the popup if the visitor clicks the dark dimmed background outside the popup. This provides an additional way for users to dismiss the popup without having to click a specific close button.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}); // End of booking popup setup

/**
 * Activates live search suggestions for every autocomplete input field on the page. When a visitor types in the search bar, this code fetches matching results from the server and displays them in a dropdown panel below the input field. The suggestions update dynamically as the user types, providing a more interactive and efficient search experience.
 */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-autocomplete]").forEach((input) => {
    // Find the outer container of the search input field, which is expected to have the class "search-wrap". If the container is not found, we return early since we cannot display the search results panel without it.
    const wrap = input.closest(".search-wrap");
    if (!wrap) return;

    /* Create a hidden dropdown panel for search results and append it to the search input's container. This panel will be populated with search suggestions as the user types, and it will be shown or hidden based on whether there are results to display. */
    const panel = document.createElement("div");
    panel.className = "search-results";
    panel.hidden = true;
    wrap.appendChild(panel);

    let timer;  // Tracks a brief pause in typing before runnning a search.

    // Listen for every letter typed in the search input field. When the user types, we clear any existing timer and set a new one to delay the search request. This prevents sending too many requests while the user is still typing.
    input .addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      // Hide the dropdown immediately if the search input is empty, since there are no results to display. This improves the user experience by not showing an empty panel when there's no query.
      if (!q) {
        panel.hidden = true;
        return;
      }

      /* Wait a split second like 150ms after typing pauses so the site doesn't send a separate search request for every single keystoke */
   timer = setTimeout(() => {
    // Ask the server for search results matching the user's query. The query is URL-encoded to ensure that special characters are handled correctly. The server is expected to return a JSON response containing an array of matching results.
        fetch("/search/?q=" + encodeURIComponent(q))
          .then(r => r.json())
          .then(data => {
            if (!data.results.length) {
              panel.innerHTML = '<p class="search-empty">No courses found</p>';
            } else {
              // Check if a data is already selected in the date picker, and if so, include it in the search results links. This allows users to see available courses for a specific date if they have already chosen one.
              const dateField = input.form && input.form.querySelector('input[type="date"]');
              const extra = dateField && dateField.value ? "?date=" + dateField.value : "";
             // Build clickable links for each search result, including the course name and city. The links will take the user to the specific facility page for the selected course, and if a date is selected, it will be included in the URL as a query parameter.
              panel.innerHTML = data.results.map(r =>
                `<a href="/facilities/${r.id}/${extra}">
                   <strong>${r.name}</strong><span>${r.city}</span>
                 </a>`
              ).join("");
            }
            panel.hidden = false; // Reveal the dropdown panel with the search results, allowing users to see and click on the suggestions.
          });
      }, 150);
    });
    // Hide the search suggestions panel if the visitor clicks anywhere outside of the search input or the panel itself. This ensures that the dropdown is dismissed when the user interacts with other parts of the page, improving usability and preventing the panel from lingering on the screen.
    document.addEventListener("click", (event) => {
      if (!wrap.contains(event.target)) panel.hidden = true;
    });
  });
});

/**
 * Handles a temperary lockout on the code verification form. If a visitor enters the wrong code too many times, they will be locked out for a set amount of time. 
 * This code displays a countdown timer showing how long until they can try again, and automatically re-enables the form when the lockout period ends.
 */
document.addEventListener("DOMContentLoaded", () => {
  // Check if a lockout is in effect by looking for the "code-lock" element. If it doesn't exist, we return early since there's no lockout to handle.
  const lock = document.getElementById("code-lock");
  if (!lock) return;
  /* Grab the countdown display, the locked submit button, and the number of seconds remaining in the lockout period. The seconds are stored as a data attribute on the "code-lock" element, allowing the server to specify how long the lockout should last. */
  const timer = document.getElementById("code-lock-timer");
  const button = document.getElementById("verify-button");
  let seconds = Number(lock.dataset.seconds);

  /**Formats the remaining seconds into a clean "minutes:seconds" format.(e.g., 1:30) */
  const show = () => {
    const m = Math.floor(seconds / 60);                  // Calculate the number of whole minutes remaining in the lockout period.
    const s = String(seconds % 60).padStart(2, "0");     // keep ramaining seconds and pad with a leading zero if necessary for consistent display (e.g., "05" instead of "5").
    timer.textContent = m + ":" + s;                     // Udate the countdown display in the lockout popup with the formatted time, allowing users to see how much longer they must wait before they can try again.
  };

  show(); // Show the initial countdown time immediately when the lockout is first detected, so users see the starting point of the countdown without any delay.
  /* Run a repeating 1 second clock (1000ms) to count down the remaining lockout time. Each tick of the clock decreases the seconds remaining by 1, updates the display, and checks if the lockout period has ended. If the countdown reaches zero, the lockout is lifted, the popup is removed, and the submit button is re-enabled for user interaction. */
  const tick = setInterval(() => {
    seconds -= 1; // subtract one second from the remaining lockout time.

    //Once the countdown reaches zero, clear the interval to stop the clock, remove the lockout popup from the page, and re-enable the submit button so that the user can try again. This ensures that users are not stuck in a lockout state indefinitely and can resume their actions once the lockout period has expired.
    if (seconds <= 0) {
      clearInterval(tick);          // Stop the 1 second countdown clock to prevent further updates to the display or lockout state.
      lock.remove();                // Remove the lockout popup from the page, allowing users to see that they can now interact with the form again.
      button.disabled = false;      // Re-enable the submit button so that users can attempt to verify their code again, restoring normal functionality to the form after the lockout period has ended.
      return;
    }
    show();  // Otherwise, update the countdown display to show the new remaining time, keeping users informed about how much longer they must wait before they can try again.
  }, 1000);
});
