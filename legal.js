(function(){
  var r=document.documentElement,btn=document.getElementById('lang'),k='manasety-lang';
  function set(l){r.lang=l;r.dir=l==='ar'?'rtl':'ltr';try{localStorage.setItem(k,l)}catch(e){}}
  var s=null;try{s=localStorage.getItem(k)}catch(e){}
  if(location.hash==='#en')s='en';
  if(s==='en'||s==='ar')set(s);else{r.lang='ar';r.dir='rtl'}
  if(btn)btn.addEventListener('click',function(){set(r.lang==='ar'?'en':'ar')});
})();
