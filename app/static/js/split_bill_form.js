document.addEventListener('DOMContentLoaded', function () {
    const participantList = document.getElementById('participant-list');
    const addBtn = document.getElementById('add-participant-btn');
    // The counter is initialized in the template like this:
    // let participantCounter = {{ form.participants|length }};
    // We'll start from a high number here as a fallback.
    let participantCounter = 100; 

    function updateRemoveButtons() {
        const removeButtons = participantList.querySelectorAll('.remove-participant-btn');
        removeButtons.forEach(btn => {
            // Prevent adding multiple listeners to the same button
            btn.removeEventListener('click', handleRemove);
            btn.addEventListener('click', handleRemove);
        });
    }

    function handleRemove(event) {
        // Removes the entire '.participant-entry' div
        event.currentTarget.closest('.participant-entry').remove();
    }

    if (addBtn) {
        addBtn.addEventListener('click', function () {
            const newEntry = document.createElement('div');
            newEntry.className = 'input-group mb-2 participant-entry';

            const newIndex = participantCounter++;
            const inputId = `participants-${newIndex}`;
            const inputName = `participants-${newIndex}`;

            // Create the input field
            const input = document.createElement('input');
            input.className = 'form-control';
            input.id = inputId;
            input.name = inputName;
            input.placeholder = 'Email temanmu';
            input.type = 'text';

            // Create the remove button
            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-outline-danger remove-participant-btn';
            removeBtn.innerHTML = '<i class="bi bi-trash"></i>';
            
            newEntry.appendChild(input);
            newEntry.appendChild(removeBtn);
            
            participantList.appendChild(newEntry);
            updateRemoveButtons();
        });
    }

    // Initial setup for any buttons already on the page
    updateRemoveButtons();
});
