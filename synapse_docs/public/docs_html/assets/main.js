document.querySelectorAll('.faq-question').forEach(function(btn){btn.addEventListener('click',function(){btn.closest('.faq-item').classList.toggle('open')})});
var currentPage=window.location.pathname.split('/').pop();document.querySelectorAll('.sidebar-nav a').forEach(function(a){if(a.getAttribute('href')===currentPage)a.classList.add('active')});
