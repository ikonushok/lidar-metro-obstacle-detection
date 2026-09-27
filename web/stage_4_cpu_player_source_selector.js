"use strict";
// Route the unchanged C++-only viewer to one lazy source. No geometry or
// membership is calculated here; the existing player still consumes C++ JSON.
(()=>{
  const requested=new URLSearchParams(location.search).get("dataset");
  const selected=/^[A-Za-z0-9_-]+$/.test(requested||"")?requested:null;
  window.cpuCatalogSelectedSource=selected;
  const nativeFetch=window.fetch.bind(window);
  window.fetch=(input,init)=>input==="manifest.json"&&selected
    ?nativeFetch("/api/cpu_sources/"+encodeURIComponent(selected)+"/manifest.json",init)
    :nativeFetch(input,init);
  const selector=document.getElementById("dataset-select");
  selector.disabled=false;
  selector.onchange=()=>{if(selector.value)location.assign("/?dataset="+encodeURIComponent(selector.value)+"&v=all-sources-2")};
  nativeFetch("/datasets.json",{cache:"no-store"})
    .then(response=>{if(!response.ok)throw Error("Каталог датасетов недоступен");return response.json()})
    .then(items=>{
      if(!Array.isArray(items)||!items.length)throw Error("Каталог источников пуст");
      const ids=new Set(items.map(item=>item.id));
      if(selected&&!ids.has(selected))throw Error("Запрошенный датасет отсутствует в каталоге: "+selected);
      selector.replaceChildren();
      if(!selected){
        const option=document.createElement("option");
        option.value="";
        option.textContent="Выберите датасет";
        selector.appendChild(option);
      }
      for(const item of items){
        const option=document.createElement("option");
        option.value=item.id;
        option.textContent=item.label;
        selector.appendChild(option);
      }
      selector.value=selected||"";
    })
    .catch(error=>{
      selector.disabled=true;
      document.getElementById("error").textContent=error.message;
    });
})();
